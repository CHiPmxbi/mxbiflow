from enum import StrEnum, auto
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict

LevelID: TypeAlias = int
MonkeyName: TypeAlias = str


class Result(StrEnum):
    CORRECT = auto()
    INCORRECT = auto()
    TIMEOUT = auto()
    CANCEL = auto()


class TouchEvent(BaseModel):
    time: float
    x: int
    y: int


class BaseTrialConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    # basic config
    level: int

    # visual stimulation config
    stimulation_size: int

    # audio stimulation config
    stimulus_duration: int

    # trial lifecycle
    time_out: int
    inter_trial_interval: int

    # reward config
    reward_duration: int
    reward_delay: int


class BaseTrialData(BaseModel):
    animal: str
    trial_id: int
    current_level_trial_id: int
    trial_start_time: float
    trial_end_time: float
    result: Result
    correct_rate: float
    touch_events: list[TouchEvent]


class BaseDataToShow(BaseModel):
    name: str
    id: int
    level_id: int
    level: int
    rewards: int
    correct: int
    incorrect: int
    timeout: int


class PersistentData(BaseModel):
    rewards: int
    correct: int
    incorrect: int
    timeout: int
