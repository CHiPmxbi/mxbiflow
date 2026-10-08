"""Eye-tracker interfaces shared by all backends."""

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Protocol


class EyetrackerEnum(StrEnum):
    """Supported eye-tracker backends."""

    MX_EYE = auto()
    MOCK = auto()


@dataclass(frozen=True, slots=True)
class EyeSample:
    """One eye-tracking sample.

    Attributes
    ----------
    timestamp_ns : int
        Acquisition wall-clock timestamp in nanoseconds, as reported by the
        tracker.
    x : float
        Horizontal coordinate of the tracker's output.
    y : float
        Vertical coordinate of the tracker's output.

    Notes
    -----
    ``x``/``y`` carry the gaze coordinates supplied by the configured tracker.
    For mx-eye, these come from the SDK frame's gaze-output fields rather than
    its separate raw pupil or corneal-reflection coordinates.
    """

    timestamp_ns: int
    x: float
    y: float


class Eyetracker(Protocol):
    """Protocol for eye-tracker backends."""

    def begin(self) -> None:
        """Start the tracker connection and its sample stream."""
        ...

    def quit(self) -> None:
        """Stop the sample stream and release any resources."""
        ...

    def sample(self) -> EyeSample | None:
        """Return the latest available sample.

        Returns
        -------
        EyeSample | None
            The most recent usable sample, or ``None`` when no sample is
            available (never measured, aged out, or the stream stopped).
        """
        ...
