from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class SettlementAction(Enum):
    """Action determined by settlement logic."""

    NONE = auto()
    LEVEL_UP = auto()
    LEVEL_DOWN = auto()
    NEXT_STAGE = auto()
    PREV_STAGE = auto()


@dataclass(frozen=True)
class RateSettlementConfig:
    """Configuration for rate-based settlement.

    Parameters
    ----------
    total_levels : int
        Maximum level the animal can reach in this stage.
    min_trials : int, optional
        Minimum number of trials before level changes are evaluated.
    up_rate : float, optional
        Correct-rate threshold for leveling up.
    down_rate : float, optional
        Correct-rate threshold for leveling down.
    """

    total_levels: int
    min_trials: int = 20
    up_rate: float = 0.8
    down_rate: float = 0.2


@dataclass(frozen=True)
class RateSettlementResult:
    """Result of rate-based settlement evaluation."""

    correct_trial_count: int
    correct_rate: float
    action: SettlementAction


@dataclass(frozen=True)
class CountSettlementConfig:
    """Configuration for count-based settlement.

    Parameters
    ----------
    total_levels : int
        Maximum level the animal can reach in this stage.
    settlement_cycle : int
        Number of correct trials required per level to advance.
    """

    total_levels: int
    settlement_cycle: int


@dataclass(frozen=True)
class CountSettlementResult:
    """Result of count-based settlement evaluation."""

    correct_trial_count: int
    level_correct_trial_count: int
    action: SettlementAction


def settle_by_rate(
    is_correct: bool,
    correct_trial_count: int,
    trial_count: int,
    level: int,
    config: RateSettlementConfig,
) -> RateSettlementResult:
    """Evaluate a trial by correct rate, returning the settlement decision.

    Parameters
    ----------
    is_correct : bool
        Whether the current trial is correct.
    correct_trial_count : int
        Number of correct trials so far (before this trial).
    trial_count : int
        Total number of trials including this one.
    level : int
        Current level of the animal in this stage.
    config : RateSettlementConfig
        Settlement parameters (thresholds, stage names, etc.).

    Returns
    -------
    RateSettlementResult
        Updated counts and the action to take.
    """
    if is_correct:
        correct_trial_count += 1

    correct_rate = correct_trial_count / trial_count

    action = SettlementAction.NONE
    if trial_count >= config.min_trials:
        if correct_rate >= config.up_rate:
            if level >= config.total_levels:
                action = SettlementAction.NEXT_STAGE
            else:
                action = SettlementAction.LEVEL_UP
        elif correct_rate <= config.down_rate:
            if level > 1:
                action = SettlementAction.LEVEL_DOWN
            else:
                action = SettlementAction.PREV_STAGE

    return RateSettlementResult(
        correct_trial_count=correct_trial_count,
        correct_rate=correct_rate,
        action=action,
    )


def settle_by_count(
    is_correct: bool,
    correct_trial_count: int,
    level_correct_trial_count: int,
    level: int,
    config: CountSettlementConfig,
) -> CountSettlementResult:
    """Evaluate a trial by counting correct responses, returning the settlement decision.

    Parameters
    ----------
    is_correct : bool
        Whether the current trial is correct.
    correct_trial_count : int
        Total number of correct trials so far (before this trial).
    level_correct_trial_count : int
        Number of correct trials at the current level (before this trial).
    level : int
        Current level of the animal in this stage.
    config : CountSettlementConfig
        Settlement parameters (cycle length, stage name, etc.).

    Returns
    -------
    CountSettlementResult
        Updated counts and the action to take.
    """
    if is_correct:
        correct_trial_count += 1
        level_correct_trial_count += 1

    action = SettlementAction.NONE
    if level_correct_trial_count >= config.settlement_cycle:
        level_correct_trial_count = 0
        if level >= config.total_levels:
            action = SettlementAction.NEXT_STAGE
        else:
            action = SettlementAction.LEVEL_UP

    return CountSettlementResult(
        correct_trial_count=correct_trial_count,
        level_correct_trial_count=level_correct_trial_count,
        action=action,
    )
