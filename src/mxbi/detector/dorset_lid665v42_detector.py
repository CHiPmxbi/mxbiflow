from threading import Event, Lock, Thread, Timer
from typing import Callable

from mxbi.detector.detector import DetectionResult, Detector
from mxbi.models.rfid_animal import animal_db
from mxbi.peripheral.rfid.dorset_lid665v42 import DorsetLID665v42, Result


class DorsetLID665v42Detector(Detector):
    def __init__(
        self, theater, port: str, baudrate: int, detection_interval: float
    ) -> None:
        super().__init__(theater)
        self._port = port
        self._baudrate = baudrate
        self._scanner = DorsetLID665v42(self._port, self._baudrate)

        self._reader_thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()

        self._result: Result | None = None
        self._callback: Callable[[Result], None] | None = None

        self._detection_interval = detection_interval
        self._timer: Timer | None = None

    # -------------------------------
    # Public lifecycle methods
    # -------------------------------

    def _start_detection(self) -> None:
        self._scanner.open()
        self._callback = self._handle_result
        self._scanner.subscribe(self._callback)

        self._stop_event.clear()

        self._reader_thread = Thread(
            target=self._scanner.read,
            name="DorsetLID665v42Reader",
            daemon=True,
        )
        self._reader_thread.start()

    def _stop_detection(self) -> None:
        self._stop_event.set()

        if self._callback:
            self._scanner.unsubscribe(self._callback)
            self._callback = None

        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

        self._scanner.close()

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._reader_thread = None

    # -------------------------------
    # Internal handlers
    # -------------------------------

    def _handle_result(self, result: Result) -> None:
        animal = animal_db.root.get(result.animal_id)
        if not animal:
            return

        with self._lock:
            self._result = Result(
                animal_id=animal.name,
                detect_time=result.detect_time,
            )

            if self._timer:
                self._timer.cancel()

            self._timer = Timer(self._detection_interval, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

        self.process_detection(DetectionResult(animal.name, False))

    def _on_timeout(self) -> None:
        with self._lock:
            if self._stop_event.is_set():
                return

            self._result = None
            self._timer = None

        self.process_detection(DetectionResult(None, False))
