from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto
from threading import Lock
from typing import Callable, Deque

from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE, Serial, SerialException


class ProtocolState(StrEnum):
    WAIT_FOR_START = auto()
    IN_FRAME = auto()
    AFTER_ESCAPE = auto()
    AWAIT_TRAILER = auto()


START = b"\x02"
STOP = b"\x03"
DLE = b"\x10"


@dataclass
class Frame:
    header: bytes = field(default_factory=lambda: DLE + START)
    payload: bytes = b""
    footer: bytes = field(default_factory=lambda: DLE + STOP)
    checksum: bytes = b"\x00"


@dataclass
class FrameData:
    host: bytes
    unit: bytes
    command: bytes
    data: bytes


@dataclass
class Result:
    detect_time: float
    animal_id: str


class _LID665v42FrameParser:
    """State machine that understands the Dorset LID665v42 frame structure."""

    def __init__(self) -> None:
        self._state = ProtocolState.WAIT_FOR_START
        self._frame_buffer = bytearray()
        self._frame_started_at = 0.0
        self._last_error: str = ""

    def reset(self) -> None:
        self._state = ProtocolState.WAIT_FOR_START
        self._frame_buffer.clear()
        self._frame_started_at = 0.0

    @property
    def last_error(self) -> str:
        return self._last_error

    def record_error(self, message: str) -> None:
        self._last_error = message

    def feed(self, byte: bytes) -> Result | None:
        """Consume a single byte and return a complete frame when available"""
        match self._state:
            case ProtocolState.WAIT_FOR_START:
                self._handle_wait_for_start(byte)
                return None
            case ProtocolState.IN_FRAME:
                self._handle_in_frame(byte)
                return None
            case ProtocolState.AFTER_ESCAPE:
                self._handle_after_escape(byte)
                return None
            case ProtocolState.AWAIT_TRAILER:
                return self._handle_trailer(byte)
            case _:
                self._last_error = f"Unhandled protocol state: {self._state}"
                self.reset()
                return None

    def _handle_wait_for_start(self, byte: bytes) -> None:
        if byte == START:
            self._frame_started_at = datetime.now().timestamp()
            self._frame_buffer.extend(DLE)
            self._frame_buffer.extend(byte)
            self._state = ProtocolState.IN_FRAME
        else:
            self._last_error = f"Expected {START!r} but received {byte!r}"

    def _handle_in_frame(self, byte: bytes) -> None:
        if byte == DLE:
            self._frame_buffer.extend(DLE)
            self._state = ProtocolState.AFTER_ESCAPE
            return

        self._frame_buffer.extend(byte)

    def _handle_after_escape(self, byte: bytes) -> None:
        if byte == STOP:
            self._frame_buffer.extend(byte)
            self._state = ProtocolState.AWAIT_TRAILER
            return

        self._frame_buffer.extend(byte)
        self._state = ProtocolState.IN_FRAME

    def _handle_trailer(self, byte: bytes) -> Result | None:
        self._frame_buffer.extend(byte)
        return self._build_result()

    def _build_result(self) -> Result | None:
        try:
            result = self._parse_frame(
                bytes(self._frame_buffer), self._frame_started_at
            )
            self._last_error = ""
            return result
        except ValueError as e:
            self._last_error = str(e)
            return None
        finally:
            self.reset()

    def _parse_frame(self, data: bytes, started_at: float) -> Result:
        if len(data) < 6:
            raise ValueError("Received frame shorter than protocol minimum")

        if not data.startswith(DLE + START):
            raise ValueError(f"Frame missing start marker: {data!r}")

        if data[-3:-1] != DLE + STOP:
            raise ValueError(f"Frame missing end marker: {data!r}")

        frame = Frame(
            header=data[:2],
            payload=self._unescape_payload(data[2:-3]),
            footer=data[-3:-1],
            checksum=data[-1:],
        )

        if len(frame.payload) < 3:
            raise ValueError("Frame payload missing host/unit/command fields")

        frame_data = FrameData(
            host=frame.payload[0:1],
            unit=frame.payload[1:2],
            command=frame.payload[2:3],
            data=frame.payload[3:],
        )

        # TODO: figure out hard-coded values for host and unit
        animal_id = frame_data.data.hex()[6:10]

        return Result(
            detect_time=started_at,
            animal_id=animal_id,
        )

    def _unescape_payload(self, payload: bytes) -> bytes:
        """
        Remove DLE-based escaping from a Dorset payload. The transport duplicates any
        byte that follows a DLE inside the frame so we treat the first DLE as an escape
        indicator and keep only the subsequent byte.
        """
        result = bytearray()
        i = 0
        while i < len(payload):
            byte = payload[i]
            if byte == DLE:
                i += 1
                if i >= len(payload):
                    raise ValueError("Dangling DLE escape in Dorset payload")
                result.append(payload[i])
            else:
                result.append(byte)
            i += 1
        return bytes(result)


class DorsetLID665v42:
    def __init__(
        self,
        port: str,
        baudrate: int,
        unit: str = "01",
        host: str = "FE",
    ) -> None:
        self._serial = Serial(
            port,
            baudrate,
            parity=PARITY_NONE,
            stopbits=STOPBITS_ONE,
            bytesize=EIGHTBITS,
            timeout=1,
        )
        self._unit = unit
        self._host = host
        self._protocol = _LID665v42FrameParser()
        self._rx_queue: Deque[Result] = deque()
        self._callbacks: list[Callable[[Result], None]] = []
        self._callback_lock = Lock()

    @property
    def errno(self) -> str:
        return self._protocol.last_error

    def open(self) -> None:
        if not self._serial.is_open:
            self._serial.open()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def read(self) -> None:
        """Continuously read from the serial port and store parsed frames."""
        while self._serial.is_open:
            try:
                byte = self._serial.read(1)
            except (SerialException, OSError, TypeError) as exc:
                # Closing the serial port from another thread can interrupt reads.
                self._protocol.record_error(f"Serial read aborted: {exc}")
                self._protocol.reset()
                break
            if not byte:
                continue

            frame = self._protocol.feed(byte)
            if frame is not None:
                self._rx_queue.append(frame)
                self._notify_subscribers(frame)

    def subscribe(self, callback: Callable[[Result], None]) -> None:
        with self._callback_lock:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[Result], None]) -> None:
        with self._callback_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def _notify_subscribers(self, result: Result) -> None:
        with self._callback_lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            try:
                callback(result)
            except Exception:
                # Callbacks are user code; errors must not break the read loop.
                continue


if __name__ == "__main__":
    import time

    animal_count = 0

    def on_result(result: Result):
        """Prints when an animal ID is successfully parsed, and increments the count"""
        global animal_count
        animal_count += 1
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(result.detect_time))
        print(f"[{t}] 🐑 Animal detected #{animal_count}: ID={result.animal_id}")

    PORT = "/dev/cu.usbserial-0001"
    BAUDRATE = 19200

    reader = DorsetLID665v42(port=PORT, baudrate=BAUDRATE)

    reader.subscribe(on_result)

    try:
        reader.open()
        print(f"✅ Serial port {PORT} opened with baudrate {BAUDRATE}")
        print(
            "📡 Listening for Dorset LID665v42 data frames... (Press Ctrl+C to stop)\n"
        )

        reader.read()

    except KeyboardInterrupt:
        print("\n🛑 Manually stopped by user.")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        reader.close()
        print(f"🔌 Serial port closed. Total animals detected: {animal_count}")
