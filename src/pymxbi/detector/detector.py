from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Callable, Protocol


class DetectorEnum(StrEnum):
    MOCK = auto()
    STANDARD_GATE = auto()
    RFID_CONTINUOUS = auto()
    BEAMBREAK_CONTINUOUS = auto()
    FUSION_CONTINUOUS = auto()


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
    ANIMAL_LEFT = auto()
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

    timestamp: float = 0.0
    animal_id: str | None = None
    animal_name: str | None = None
    error: bool = False


class Detector(Protocol):
    def register_event(
        self, event: DetectorEvent, callback: Callable[[DetectionResult], None]
    ) -> None: ...

    def register_animal(self, animals: dict[str, str]) -> None: ...

    def begin(self) -> None: ...

    def quit(self) -> None: ...

    @property
    def current_animal(self) -> str | None: ...

    @property
    def animal_list(self) -> list[str]: ...
