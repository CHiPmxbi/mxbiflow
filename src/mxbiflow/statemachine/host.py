"""What the host gets back from a trial, as cogforge's ``src/model/host.ts`` does.

The host gives a stage's machine its parameter values, runs the trial and reads its
outcome and its record. Which values, and what the outcome does to the animal's level,
is the stage's own Python.
"""

from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from ..scene.settlement import SettlementAction
from .models import Stage
from .runner import Trial

type Outcome = Literal["correct", "incorrect", "miss", "none"]
type Action = Literal["none", "level up", "level down", "next stage", "previous stage"]

ACTIONS: dict[SettlementAction, Action] = {
    SettlementAction.NONE: "none",
    SettlementAction.LEVEL_UP: "level up",
    SettlementAction.LEVEL_DOWN: "level down",
    SettlementAction.NEXT_STAGE: "next stage",
    SettlementAction.PREV_STAGE: "previous stage",
}


class Entered(BaseModel):
    state: str
    t: float


class Logged(BaseModel):
    t: float
    text: str


class TrialRecord(BaseModel):
    """One line of ``result.jsonl``: cogforge's ``TrialRecord``, and the host's own.

    ``trial``, ``stage``, ``values``, ``outcome``, ``states`` and ``events`` are
    cogforge's; the animal, its level, what settling the trial decided and what the
    stage noted about it are mxbiflow's.
    """

    animal: str
    trial: int
    stage: str
    level: int
    values: dict[str, float | str]
    outcome: Outcome
    action: Action
    states: list[Entered]
    events: list[Logged]
    # What the stage's own Python code noted about the trial (MachineScene.note).
    extra: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])


def outcome_of(stage: Stage, trial: Trial) -> Outcome:
    """The outcome of the last state entered that has one."""
    for visit in reversed(trial.visited):
        outcome = stage.outcomes.get(visit.state)
        if outcome is not None:
            return outcome.value
    return "none"
