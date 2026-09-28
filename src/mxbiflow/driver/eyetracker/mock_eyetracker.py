"""Mock eye tracker for testing and development.

This backend does not talk to any hardware. Samples are provided by the
caller, which lets experiments and tests run on machines without a tracker.
"""

import time

from .eyetracker import EyeSample


class MockEyetracker:
    """Eyetracker backend that reports caller-provided samples.

    Implements the :class:`Eyetracker` protocol.

    Samples never age out: the value set through :meth:`set_sample` keeps being
    reported until it is replaced, cleared, or :meth:`quit` is called.
    """

    def __init__(self) -> None:
        self._sample: EyeSample | None = None

    def begin(self) -> None:
        """Start the tracker (no-op)."""

    def quit(self) -> None:
        """Drop the current sample."""
        self._sample = None

    def sample(self) -> EyeSample | None:
        """Return the sample set through :meth:`set_sample`, if any."""
        return self._sample

    def set_sample(
        self, x: float, y: float, *, timestamp_ns: int | None = None
    ) -> None:
        """Report a sample at ``(x, y)``.

        Parameters
        ----------
        x : float
            Horizontal coordinate in the tracker's output space.
        y : float
            Vertical coordinate in the tracker's output space.
        timestamp_ns : int | None, default=None
            Acquisition timestamp in nanoseconds; defaults to now.
        """
        self._sample = EyeSample(
            timestamp_ns=time.time_ns() if timestamp_ns is None else timestamp_ns,
            x=x,
            y=y,
        )

    def clear(self) -> None:
        """Report no sample."""
        self._sample = None
