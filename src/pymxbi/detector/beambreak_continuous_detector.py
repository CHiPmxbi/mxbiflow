from threading import Event, Thread
from time import sleep, time

from ..peripheral.beam_break_sensor.beam_break_sensor import BeamBreakSensor
from .detector import DetectionResult
from .continuous_detector import ContinuousDetector


class BeambreakContinuousDetector(ContinuousDetector):
    def __init__(
        self,
        beam_break_sensor: BeamBreakSensor,
    ) -> None:
        super().__init__()

        self._beam_break_sensor = beam_break_sensor
        self._active_animal: str | None = None

        self._stop_event = Event()
        self._worker_thread: Thread = Thread(target=self._worker)

    def register_animal(self, animals: dict[str, str]) -> None:
        super().register_animal(animals)

        self._active_animal = next(iter(animals.values()))

    def begin(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()

        self._worker_thread.start()

    def quit(self) -> None:
        self._stop_event.set()
        try:
            self._beam_break_sensor.close()
        finally:
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join()

    def _worker(self) -> None:
        if self._active_animal is None:
            raise ValueError("No animals registered")

        active_animal_name: str = self._active_animal

        while not self._stop_event.is_set():
            try:
                beam_broken = self._beam_break_sensor.read()
                self.process_detection(
                    DetectionResult(
                        timestamp=time(),
                        animal_name=active_animal_name if beam_broken else None,
                        error=False,
                    )
                )
            except Exception:
                self.process_detection(DetectionResult(timestamp=time(), error=True))

            sleep(1)
