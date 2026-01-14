"""Rewarder interfaces and reward specifications.

This module defines immutable reward specifications and a :class:`Rewarder`
protocol that backend implementations should follow.

Notes
-----
Use :func:`by_time` or :func:`by_count` to construct a reward specification.
"""

from typing import Protocol, Literal, TypeAlias, TypeVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimeRewardSpec:
    """Time-based reward specification.

    Parameters
    ----------
    duration_ms : int
        Duration of the reward in milliseconds.

    Attributes
    ----------
    kind : {"time"}
        Discriminator used when serializing or pattern-matching.
    duration_ms : int
        Duration of the reward in milliseconds.
    """

    kind: Literal["time"] = "time"
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class CountRewardSpec:
    """Count-based reward specification.

    Parameters
    ----------
    count : int
        Number of discrete reward events to dispense.

    Attributes
    ----------
    kind : {"count"}
        Discriminator used when serializing or pattern-matching.
    count : int
        Number of discrete reward events to dispense.
    """

    kind: Literal["count"] = "count"
    count: int = 0


RewardSpec: TypeAlias = TimeRewardSpec | CountRewardSpec
"""Union of all supported reward specifications."""


def by_time(duration_ms: int) -> TimeRewardSpec:
    """Create a time-based reward specification.

    Parameters
    ----------
    duration_ms : int
        Duration of the reward in milliseconds.

    Returns
    -------
    TimeRewardSpec
        The created time-based reward specification.
    """

    return TimeRewardSpec(duration_ms=duration_ms)


def by_count(count: int) -> CountRewardSpec:
    """Create a count-based reward specification.

    Parameters
    ----------
    count : int
        Number of discrete reward events to dispense.

    Returns
    -------
    CountRewardSpec
        The created count-based reward specification.
    """

    return CountRewardSpec(count=count)


TSpec = TypeVar("TSpec", bound=RewardSpec, contravariant=True)


class Rewarder(Protocol[TSpec]):
    """Protocol for rewarder backends.

    Implementations are expected to manage any hardware/resources needed to
    dispense rewards (e.g., pumps, solenoids, etc.).
    """

    def open(self) -> None:
        """Initialize the rewarder and prepare it for operation."""
        ...

    def give_reward(self, spec: TSpec) -> None:
        """Dispense a reward as described by ``spec``.

        Parameters
        ----------
        spec : RewardSpec
            Reward specification (time- or count-based).
        """

        ...

    def stop_reward(self) -> None:
        """Stop dispensing a reward."""
        ...

    def close(self) -> None:
        """Release any resources held by the rewarder."""
        ...
