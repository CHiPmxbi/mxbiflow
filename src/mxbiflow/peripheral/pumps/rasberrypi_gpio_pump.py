from queue import Empty, Queue
from threading import Event, Thread
from time import sleep

from gpiozero import DigitalOutputDevice

from mxbi.utils.logger import logger

PUMP_PIN: int = 13


class RasberryPiGPIOPump:
    def __init__(self) -> None:
        try:
            self._pump = DigitalOutputDevice(
                PUMP_PIN, active_high=True, initial_value=False
            )
        except Exception as exc:  # pragma: no cover - hardware specific failure
            logger.error(f"Failed to initialize gpiozero DigitalOutputDevice: {exc}")
            raise SystemExit(1) from exc

        self._stop_event: Event = Event()
        self._task_queue: Queue[int | None] = Queue()
        self._worker_thread: Thread = Thread(target=self._worker, daemon=True)

        self._worker_thread.start()

    def _worker(self) -> None:
        while True:
            duration = self._task_queue.get()
            if duration is None:
                break

            self._stop_event.clear()
            self._give_reward(duration)

        self._pump.off()

    def _give_reward(self, duration: int) -> None:
        try:
            duration_sec = max(duration, 0) / 1000
            self._pump.on()

            check_interval = 0.1
            elapsed = 0.0

            while elapsed < duration_sec and not self._stop_event.is_set():
                sleep_time = min(check_interval, duration_sec - elapsed)
                sleep(sleep_time)
                elapsed += sleep_time

        except Exception as exc:  # pragma: no cover - hardware specific failure
            logger.warning(f"Error in _give_reward: {exc}")
        finally:
            try:
                self._pump.off()
            except Exception as exc:  # pragma: no cover - hardware specific failure
                logger.warning(f"Error while turning pump off: {exc}")

    def give_reward(self, duration: int) -> None:
        self._task_queue.put(duration)

    def stop_reward(self, all: bool = False) -> None:
        self._stop_event.set()
        try:
            self._pump.off()
        except Exception as exc:  # pragma: no cover - hardware specific failure
            logger.warning(f"Error while turning pump off: {exc}")

        if all:
            self._drain_queue()

    def _drain_queue(self) -> None:
        while True:
            try:
                self._task_queue.get_nowait()
            except Empty:
                break

    def close(self) -> None:
        self.stop_reward(True)
        self._task_queue.put(None)

        self._worker_thread.join(timeout=1.0)

        try:
            self._pump.close()
        except Exception as exc:  # pragma: no cover - hardware specific failure
            logger.warning(f"Error while closing pump device: {exc}")

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def reverse(self) -> None:
        raise NotImplementedError("Reverse operation is not supported by this device")
