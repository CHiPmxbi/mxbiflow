"""Pump abstractions used by reward delivery hardware."""

from typing import Protocol
from enum import Enum, auto


class Direction(Enum):
    """Pump direction indicator.

    Attributes
    ----------
    FORWARD
        Forward direction.
    REVERSE
        Reverse direction.
    """

    FORWARD = auto()
    REVERSE = auto()


class Pump(Protocol):
    """Protocol for pump peripherals."""

    def open(self) -> None:
        """Initialize the pump and prepare it for operation."""
        ...

    def start(self) -> None:
        """Start the pump operation."""
        ...

    def stop(self) -> None:
        """Stop the pump operation."""
        ...

    def close(self) -> None:
        """Release any resources held by the pump."""
        ...

    def set_direction(self, direction: Direction) -> None:
        """Set the pump's direction (if applicable).

        Parameters
        ----------
        direction : Direction
            Desired pump direction.
        """
        ...

    def toggle_direction(self) -> None:
        """Toggle the pump's direction (if applicable)."""
        ...
