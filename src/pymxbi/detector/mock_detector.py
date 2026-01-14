"""Mock detector implementation for testing and development."""

from pymxbi.detector.detector import Detector


class MockDetector(Detector):
    """Detector stub that performs no I/O."""

    def __init__(self) -> None:
        """Create a mock detector with an empty animal database."""
        super().__init__({})

    def _begin(self) -> None:
        """Begin detection (no-op)."""
        ...

    def _quit(self) -> None:
        """Stop detection (no-op)."""
        ...
