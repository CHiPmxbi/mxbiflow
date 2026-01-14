"""Detector abstractions and the built-in detector state machine."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum, auto
from threading import Lock
from typing import Callable


class DetectorState(StrEnum):
    """Detector finite states.

    Attributes
    ----------
    IDLE
        No animal is currently detected.
    ANIMAL_PRESENT
        An animal is currently detected.
    FAULT
        A fault was detected and the detector is in an error state.
    """

    IDLE = auto()
    ANIMAL_PRESENT = auto()
    FAULT = auto()


class DetectorEvent(StrEnum):
    """Detector events emitted on state transitions.

    Attributes
    ----------
    ANIMAL_ENTERED
        Transition from idle to an animal being present.
    ANIMAL_RETURNED
        Animal reappeared after a brief absence.
    ANIMAL_CHANGED
        A different animal replaced the currently detected one.
    ANIMAL_LEFT
        Transition from an animal being present to idle.
    ANIMAL_REMAINED
        The same animal remains present across cycles.
    FAULT_DETECTED
        A fault occurred while detecting.
    """

    ANIMAL_ENTERED = auto()
    ANIMAL_RETURNED = auto()
    ANIMAL_CHANGED = auto()
    ANIMAL_LEFT = auto()
    ANIMAL_REMAINED = auto()
    FAULT_DETECTED = auto()


@dataclass
class DetectionResult:
    """Detection result from a detector input cycle.

    Parameters
    ----------
    animal_name : str | None, default=None
        Name of the detected animal, if any.
    error : bool, default=False
        Whether a fault was detected while reading inputs.
    """

    animal_name: str | None = None
    error: bool = False


class DetectorStateMachine:
    """State machine that drives detector events.

    Parameters
    ----------
    detector : Detector
        Detector instance used to emit events to registered callbacks.
    """

    def __init__(self, detector: Detector) -> None:
        """Initialize with a detector for event emission."""
        self.detector = detector

        self.current_state: DetectorState = DetectorState.IDLE
        self.current_animal: str | None = None
        self.last_seen_animal: str | None = None

    def transition(self, detection_result: DetectionResult) -> None:
        """Apply a detection result and advance the state machine."""
        match (self.current_state, detection_result):
            case (_, DetectionResult(error=True)):
                self._handle_error()

            # NO_ANIMAL -> ANIMAL_PRESENT
            case (DetectorState.IDLE, DetectionResult(animal_name=animal_name)) if (
                animal_name is not None
            ):
                if animal_name != self.last_seen_animal:
                    self._handle_animal_entered(animal_name)
                else:
                    self._handle_animal_returned(animal_name)

            # NO_ANIMAL -> NO_ANIMAL
            case (DetectorState.IDLE, DetectionResult(animal_name=None)):
                pass

            # ANIMAL_PRESENT -> NO_ANIMAL
            case (DetectorState.ANIMAL_PRESENT, DetectionResult(animal_name=None)):
                self._handle_animal_left()

            # ANIMAL_PRESENT -> DIFFERENT_ANIMAL
            case (
                DetectorState.ANIMAL_PRESENT,
                DetectionResult(animal_name=animal_name),
            ) if animal_name is not None and animal_name != self.current_animal:
                self._handle_animal_changed(animal_name)

            # ANIMAL_PRESENT -> SAME_ANIMAL
            case (
                DetectorState.ANIMAL_PRESENT,
                DetectionResult(animal_name=animal_name),
            ) if animal_name is not None and animal_name == self.current_animal:
                self._handle_animal_stayed(animal_name)

            # ERROR -> ANY_STATE
            case (DetectorState.FAULT, DetectionResult(animal_name=animal_name)):
                self._handle_recovery_from_error(animal_name)

            case _:
                print(
                    f"Unexpected state transition: {self.current_state}, {detection_result}"
                )

    def _handle_error(self) -> None:
        """Move to fault state and emit the fault event."""
        if self.current_state != DetectorState.FAULT:
            self.current_animal = None
            self.current_state = DetectorState.FAULT
            self.detector._emit_event(DetectorEvent.FAULT_DETECTED, "")

    def _handle_animal_entered(self, animal: str) -> None:
        """Handle an animal entering from idle state."""
        self.current_state = DetectorState.ANIMAL_PRESENT

        self.current_animal = animal
        self.last_seen_animal = self.current_animal

        self.detector._emit_event(DetectorEvent.ANIMAL_ENTERED, animal)

    def _handle_animal_returned(self, animal: str) -> None:
        """Handle an animal returning after a brief absence."""
        self.current_state = DetectorState.ANIMAL_PRESENT

        self.current_animal = animal
        self.last_seen_animal = self.current_animal

        self.detector._emit_event(DetectorEvent.ANIMAL_RETURNED, animal)

    def _handle_animal_left(self) -> None:
        """Handle the current animal leaving."""
        assert self.current_animal is not None
        left_animal = self.current_animal
        self.current_state = DetectorState.IDLE
        self.current_animal = None
        self.detector._emit_event(DetectorEvent.ANIMAL_LEFT, left_animal)

    def _handle_animal_changed(self, new_animal_name: str) -> None:
        """Handle a different animal replacing the current one."""
        self.last_seen_animal = self.current_animal
        self.current_animal = new_animal_name

        self.detector._emit_event(DetectorEvent.ANIMAL_CHANGED, new_animal_name)

    def _handle_animal_stayed(self, animal_name: str) -> None:
        """Handle the same animal remaining present."""
        self.detector._emit_event(DetectorEvent.ANIMAL_REMAINED, animal_name)

    def _handle_recovery_from_error(self, animal_name: str | None) -> None:
        """Recover from fault state based on current detection."""
        if animal_name is None:
            self.current_state = DetectorState.IDLE
            self.current_animal = None
        else:
            self._handle_animal_entered(animal_name)


class Detector(ABC):
    """Abstract detector base class.

    Parameters
    ----------
    animal_db : dict[str, str]
        Mapping from animal ID to animal name.
    """

    def __init__(self, animal_db: dict[str, str]) -> None:
        """Initialize with a mapping from animal ID to animal name."""
        self._callbacks: dict[DetectorEvent, list[Callable[[str], None]]] = {}

        self._state_lock = Lock()
        self._state_machine = DetectorStateMachine(self)

        self.animal_db = animal_db

    def register_event(
        self, event: DetectorEvent, callback: Callable[[str], None]
    ) -> None:
        """Register a callback for a detector event.

        Parameters
        ----------
        event : DetectorEvent
            Event type to register for.
        callback : Callable[[str], None]
            Function called with the detected animal name (or ``""`` for faults).
        """
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _emit_event(self, event: DetectorEvent, animal_name: str) -> None:
        """Emit an event to registered callbacks."""
        if event not in self._callbacks:
            return
        for callback in self._callbacks[event]:
            callback(animal_name)

    def process_detection(self, detection_result: DetectionResult) -> None:
        """Process a detection result in a thread-safe manner.

        Parameters
        ----------
        detection_result : DetectionResult
            Output from a single detection cycle (sensor/reader read).
        """
        with self._state_lock:
            self._state_machine.transition(detection_result)

    @abstractmethod
    def begin(self) -> None: ...

    @abstractmethod
    def quit(self) -> None: ...

    @property
    def current_animal(self) -> str | None:
        """Return the currently detected animal name, if any."""
        return self._state_machine.current_animal

    @property
    def current_state(self) -> DetectorState:
        """Return the current detector state."""
        return self._state_machine.current_state
