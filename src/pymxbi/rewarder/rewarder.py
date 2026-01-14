"""Rewarder interface definition.

This module defines a :class:`~pymxbi.rewarder.rewarder.Rewarder` protocol that
reward backends should implement (e.g., liquid pumps, solenoids, feeders).
"""

from typing import Protocol


class Rewarder(Protocol):
    """Protocol for rewarder backends.

    Implementations are expected to manage any hardware/resources needed to
    dispense rewards (e.g., pumps, solenoids, etc.).
    """

    def open(self) -> None:
        """Initialize the rewarder and prepare it for operation."""
        ...

    def give_reward(self, duration_ms: int) -> None:
        """Dispense a time-based reward.

        Parameters
        ----------
        duration_ms : int
            Duration of the reward in milliseconds.
        """

        ...

    def give_reward_by_volume(self, volume_ul: int) -> None:
        """Dispense a reward based on the given volume.

        Parameters
        ----------
        volume_ul : int
            Volume of liquid to dispense in microliters.
        """
        ...

    def give_reward_by_count(self, count: int) -> None:
        """Dispense a reward based on the given count.

        Parameters
        ----------
        count : int
            Number of reward units to dispense.
        """
        ...

    def stop_reward(self) -> None:
        """Stop dispensing a reward."""
        ...

    def close(self) -> None:
        """Release any resources held by the rewarder."""
        ...
