"""Mock rewarder implementation for testing and development.

This rewarder does not control any hardware. Instead, it logs calls to its
methods to a provided ``loguru.Logger`` sink.
"""

from pymxbi.rewarder.rewarder import TimeRewardSpec
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

    def give_reward(self, spec: TimeRewardSpec) -> None:
        """Log dispensing a time-based reward.

        Parameters
        ----------
        spec : TimeRewardSpec
            Time-based reward specification.
        """

        self._sink.info(
            f"MockRewarder giving time-based reward for {spec.duration_ms} ms."
        )

    def stop_reward(self) -> None:
        """Stop dispensing a reward (no-op other than logging)."""
        self._sink.info("MockRewarder stopped reward.")

    def close(self) -> None:
        """Close the rewarder (no-op other than logging)."""
        self._sink.info("MockRewarder closed.")
