from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum, auto
from threading import Lock
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from mxbi.theater import Theater


class DetectorState(StrEnum):
    NO_ANIMAL = auto()
    ANIMAL_PRESENT = auto()
    ERROR = auto()


class DetectorEvent(StrEnum):
    ANIMAL_ENTERED = auto()
    ANIMAL_RETUREND = auto()
    ANIMAL_CHANGED = auto()
    ANIMAL_LEFT = auto()
    ERROR_DETECTED = auto()


@dataclass
class DetectionResult:
    animal_name: str | None = None
    error: bool = False


class AnimalDetectorStateMachine:
    def __init__(self, detector: "Detector") -> None:
        self.detector = detector

        self.current_state: DetectorState = DetectorState.NO_ANIMAL
        self.current_animal: str | None = None
        self.last_animal: str | None = None

    def transition(self, detection_result: DetectionResult) -> None:
        match (self.current_state, detection_result):
            case (_, DetectionResult(error=True)):
                self._handle_error()

            # NO_ANIMAL -> ANIMAL_PRESENT
            case (DetectorState.NO_ANIMAL, DetectionResult(animal_name=animal)) if (
                animal is not None
            ):
                if animal != self.last_animal:
                    self._handle_animal_entered(animal)
                else:
                    self._handle_animal_returned(animal)

            # NO_ANIMAL -> NO_ANIMAL
            case (DetectorState.NO_ANIMAL, DetectionResult(animal_name=None)):
                pass

            # ANIMAL_PRESENT -> NO_ANIMAL
            case (DetectorState.ANIMAL_PRESENT, DetectionResult(animal_name=None)):
                self._handle_animal_left()

            # ANIMAL_PRESENT -> DIFFERENT_ANIMAL
            case (
                DetectorState.ANIMAL_PRESENT,
                DetectionResult(animal_name=animal),
            ) if animal is not None and animal != self.current_animal:
                self._handle_animal_changed(animal)

            # ANIMAL_PRESENT -> SAME_ANIMAL
            case (
                DetectorState.ANIMAL_PRESENT,
                DetectionResult(animal_name=animal),
            ) if animal == self.current_animal:
                pass

            # ERROR -> ANY_STATE
            case (DetectorState.ERROR, DetectionResult(animal_name=animal)):
                self._handle_recovery_from_error(animal)

            case _:
                print(
                    f"Unexpected state transition: {self.current_state}, {detection_result}"
                )

    def _handle_error(self) -> None:
        if self.current_state != DetectorState.ERROR:
            self.current_state = DetectorState.ERROR
            self.detector._emit_event(DetectorEvent.ERROR_DETECTED, "")

    def _handle_animal_entered(self, animal: str) -> None:
        self.current_state = DetectorState.ANIMAL_PRESENT
        self.last_animal = animal
        self.current_animal = animal
        self.detector._emit_event(DetectorEvent.ANIMAL_ENTERED, animal)

    def _handle_animal_returned(self, animal: str) -> None:
        self.current_state = DetectorState.ANIMAL_PRESENT
        self.last_animal = animal
        self.current_animal = animal
        self.detector._emit_event(DetectorEvent.ANIMAL_RETUREND, animal)

    def _handle_animal_left(self) -> None:
        assert self.current_animal is not None
        left_animal = self.current_animal
        self.current_state = DetectorState.NO_ANIMAL
        self.current_animal = None
        self.detector._emit_event(DetectorEvent.ANIMAL_LEFT, left_animal)

    def _handle_animal_changed(self, new_animal_name: str) -> None:
        self.current_animal = new_animal_name
        self.detector._emit_event(DetectorEvent.ANIMAL_CHANGED, new_animal_name)

    def _handle_recovery_from_error(self, animal_name: str | None) -> None:
        if animal_name is None:
            self.current_state = DetectorState.NO_ANIMAL
            self.current_animal = None
        else:
            self.current_state = DetectorState.ANIMAL_PRESENT
            self.current_animal = animal_name
            self.detector._emit_event(DetectorEvent.ANIMAL_ENTERED, animal_name)


class Detector(ABC):
    def __init__(self, theater: "Theater") -> None:
        self._theater = theater
        self._callbacks: dict[DetectorEvent, list[Callable[[str], None]]] = {}

        self._is_running: bool = False
        self._state_lock = Lock()
        self._state_machine = AnimalDetectorStateMachine(self)

    def start(self) -> None:
        if self._is_running:
            return

        self._is_running = True
        self._start_detection()

    def quit(self) -> None:
        if not self._is_running:
            return

        self._is_running = False
        self._stop_detection()

    def register_event(
        self, event: DetectorEvent, callback: Callable[[str], None]
    ) -> None:
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _emit_event(self, event: DetectorEvent, animal_name: str) -> None:
        if event not in self._callbacks:
            return
        for callback in self._callbacks[event]:
            callback(animal_name)

    def process_detection(self, detection_result: DetectionResult) -> None:
        if not self._is_running:
            return

        with self._state_lock:
            self._state_machine.transition(detection_result)

    @abstractmethod
    def _start_detection(self) -> None: ...

    @abstractmethod
    def _stop_detection(self) -> None: ...

    @property
    def current_animal(self) -> str | None:
        return self._state_machine.current_animal

    @property
    def current_state(self) -> DetectorState:
        return self._state_machine.current_state
