"""Mock rewarder implementation for testing and development.

This rewarder does not control any hardware. Instead, it logs calls to its
methods to a provided ``loguru.Logger`` sink.
"""

from loguru import Logger


class MockRewarder:
    """A rewarder backend that logs reward actions.

    Parameters
    ----------
    sink : loguru.Logger
        Logger used to record rewarder operations.
    """

    def __init__(self, sink: Logger) -> None:
        """Create a new mock rewarder.

        Parameters
        ----------
        sink : loguru.Logger
            Logger used to record rewarder operations.
        """

        self._sink = sink

    def open(self) -> None:
        """Initialize the rewarder (no-op other than logging)."""
        self._sink.info("MockRewarder opened.")

    def give_reward(self, duration_ms: int) -> None:
        """Log dispensing a time-based reward.

        Parameters
        ----------
        duration_ms : int
            Duration of the reward in milliseconds.
        """

        self._sink.info(f"MockRewarder giving time-based reward for {duration_ms} ms.")

    def give_reward_by_volume(self, volume_ul: int) -> None:
        """Log dispensing a volume-based reward.

        Parameters
        ----------
        volume_ul : int
            Volume of liquid to dispense in microliters.
        """
        self._sink.info(f"MockRewarder giving volume-based reward: {volume_ul} uL.")

    def give_reward_by_count(self, count: int) -> None:
        """Log dispensing a count-based reward.

        Parameters
        ----------
        count : int
            Number of reward units to dispense.
        """
        self._sink.info(f"MockRewarder giving count-based reward: {count}.")

    def stop_reward(self) -> None:
        """Stop dispensing a reward (no-op other than logging)."""
        self._sink.info("MockRewarder stopped reward.")

    def close(self) -> None:
        """Close the rewarder (no-op other than logging)."""
        self._sink.info("MockRewarder closed.")
