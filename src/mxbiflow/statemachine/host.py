"""What the host does around each trial, as cogforge's ``src/model/host.ts`` does.

Draw the trial's parameters from the animal's level, work out the outcome, record the
trial, and move the animal between levels and stages. Pure functions; the random source
is passed in so tests can fix it.
"""

import math
import random as random_module
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from ..scene.settlement import (
    CountSettlementConfig,
    RateSettlementConfig,
    SettlementAction,
    settle_by_count,
    settle_by_rate,
)
from .models import (
    Animal,
    CountProgression,
    Experiment,
    Factor,
    Order,
    RateProgression,
    Row,
    Stage,
    Value1,
    Value2,
)
from .runner import Trial, Values, default_values

type Outcome = Literal["correct", "incorrect", "miss", "none"]
type Action = Literal["none", "level up", "level down", "next stage", "previous stage"]

ACTIONS: dict[SettlementAction, Action] = {
    SettlementAction.NONE: "none",
    SettlementAction.LEVEL_UP: "level up",
    SettlementAction.LEVEL_DOWN: "level down",
    SettlementAction.NEXT_STAGE: "next stage",
    SettlementAction.PREV_STAGE: "previous stage",
}


@dataclass(frozen=True)
class Progress:
    """Where an animal is: stage and level indices, and its counts at this level."""

    stage: int
    level: int
    trials: int = 0
    correct: int = 0
    # For each factor that takes its rows in turn, the next row.
    cursors: Mapping[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True)
class Draw:
    """A trial's parameters, and the row each factor drew."""

    factors: dict[str, str]
    values: Values
    cursors: dict[str, int]


class Entered(BaseModel):
    state: str
    t: float


class Logged(BaseModel):
    t: float
    text: str


class TrialRecord(BaseModel):
    """One line of ``result.jsonl``; cogforge's ``TrialRecord``."""

    animal: str
    trial: int
    stage: str
    level: str
    factors: dict[str, str]
    values: dict[str, float | str]
    outcome: Outcome
    action: Action
    states: list[Entered]
    events: list[Logged]
    # What the stage's own Python code noted about the trial (MachineScene.note).
    extra: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])


def start_of(experiment: Experiment, animal: Animal) -> Progress:
    stages = [stage.name for stage in experiment.stages]
    stage = stages.index(animal.stage) if animal.stage in stages else 0
    levels = [level.name for level in experiment.stages[stage].levels]
    level = levels.index(animal.level) if animal.level in levels else 0
    return Progress(stage=stage, level=level)


def _round(value: float) -> int:
    """Round half up, as JavaScript's ``Math.round``."""
    return math.floor(value + 0.5)


def draw_trial(
    experiment: Experiment,
    values: Mapping[str, float | str],
    progress: Progress,
    random: Callable[[], float] = random_module.random,
) -> Draw:
    """The parameters of the animal's next trial.

    Defaults, then the level's values in order (one random number per range or
    choice), then one row of each factor in order, then the animal's own ``values``.
    The order and the use of random numbers are cogforge's, number for number.
    """
    if not 0 <= progress.stage < len(experiment.stages):
        raise ValueError(f"no stage {progress.stage}")
    stage = experiment.stages[progress.stage]
    if not 0 <= progress.level < len(stage.levels):
        raise ValueError(f'stage "{stage.name}": no level {progress.level}')
    level = stage.levels[progress.level]
    # Times are whole milliseconds and counts whole numbers.
    whole = {p.name for p in stage.machine.parameters if p.type in ("count", "time")}
    drawn: Values = default_values(stage.machine)
    for name, value in level.values.items():
        if isinstance(value, Value2):
            choice = value.choice
            drawn[name] = choice[
                min(len(choice) - 1, math.floor(random() * len(choice)))
            ]
        elif isinstance(value, Value1):
            low, high = value.uniform
            number = low + random() * (high - low)
            drawn[name] = _round(number) if name in whole else number
        else:
            drawn[name] = value
    factors: dict[str, str] = {}
    cursors = dict(progress.cursors)
    for factor in level.factors:
        if not factor.rows:
            continue
        cursor = cursors.get(factor.name, 0)
        row = _draw_row(factor, cursor, random)
        if factor.order is Order.cycle:
            cursors[factor.name] = cursor + 1
        factors[factor.name] = row.name
        drawn.update(row.values)
    for name, value in values.items():
        if name in drawn:
            drawn[name] = value
    return Draw(factors=factors, values=drawn, cursors=cursors)


def _draw_row(factor: Factor, cursor: int, random: Callable[[], float]) -> Row:
    if factor.order is Order.cycle:
        return factor.rows[cursor % len(factor.rows)]
    pick = random() * sum(row.weight for row in factor.rows)
    total = 0.0
    for row in factor.rows:
        total += row.weight
        if pick < total:
            return row
    # A random number of nearly 1 can round past the last sum.
    for row in reversed(factor.rows):
        if row.weight > 0:
            return row
    raise ValueError(f'factor "{factor.name}" has no row to draw')


def outcome_of(stage: Stage, trial: Trial) -> Outcome:
    """The outcome of the last state entered that has one."""
    for visit in reversed(trial.visited):
        outcome = stage.outcomes.get(visit.state)
        if outcome is not None:
            return outcome.value
    return "none"


def settle(
    experiment: Experiment,
    progress: Progress,
    outcome: Outcome,
    decided_by_host: Action | None = None,
) -> tuple[Progress, Action]:
    """Count the trial and decide whether the animal moves on.

    ``decided_by_host`` is what a stage's own rule decided, in place of the stage's
    ``progression``; a move it asks for that does not exist raises ``ValueError``.
    """
    stage = experiment.stages[progress.stage]
    is_correct = outcome == "correct"
    counted = replace(
        progress, trials=progress.trials + 1, correct=progress.correct + is_correct
    )
    rule = stage.progression
    decided = SettlementAction.NONE
    # mxbiflow's settlement counts levels from 1.
    if isinstance(rule, RateProgression):
        decided = settle_by_rate(
            is_correct,
            progress.correct,
            counted.trials,
            progress.level + 1,
            RateSettlementConfig(
                total_levels=len(stage.levels),
                min_trials=rule.min_trials,
                up_rate=rule.up,
                down_rate=rule.down,
            ),
        ).action
    elif isinstance(rule, CountProgression):
        decided = settle_by_count(
            is_correct,
            progress.correct,
            progress.correct,
            progress.level + 1,
            CountSettlementConfig(
                total_levels=len(stage.levels), settlement_cycle=rule.correct
            ),
        ).action
    action = ACTIONS[decided]
    if decided_by_host is not None:
        action = decided_by_host
        possible = {
            "none": True,
            "level up": progress.level < len(stage.levels) - 1,
            "level down": progress.level > 0,
            "next stage": progress.stage < len(experiment.stages) - 1,
            "previous stage": progress.stage > 0,
        }
        if not possible[action]:
            raise ValueError(
                f'stage "{stage.name}", level {progress.level + 1}: '
                f'the stage\'s rule decided "{action}", which is not possible'
            )
    if action == "level up":
        return Progress(progress.stage, progress.level + 1), action
    if action == "level down":
        return Progress(progress.stage, progress.level - 1), action
    if action == "next stage" and progress.stage < len(experiment.stages) - 1:
        return Progress(progress.stage + 1, 0), action
    if action == "previous stage" and progress.stage > 0:
        last = len(experiment.stages[progress.stage - 1].levels) - 1
        return Progress(progress.stage - 1, last), action
    return counted, "none"


def record_of(
    experiment: Experiment,
    animal: str,
    trial_number: int,
    progress: Progress,
    draw: Draw,
    trial: Trial,
    outcome: Outcome,
    action: Action,
    extra: Mapping[str, JsonValue] | None = None,
) -> TrialRecord:
    stage = experiment.stages[progress.stage]
    return TrialRecord(
        animal=animal,
        trial=trial_number,
        stage=stage.name,
        level=stage.levels[progress.level].name,
        factors=draw.factors,
        values=draw.values,
        outcome=outcome,
        action=action,
        states=[Entered(state=v.state, t=v.t) for v in trial.visited],
        events=[Logged(t=entry.t, text=entry.text) for entry in trial.log],
        extra=dict(extra or {}),
    )
