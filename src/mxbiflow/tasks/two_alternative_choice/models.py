from enum import StrEnum, auto
from typing import TypeAlias

from pydantic import BaseModel

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
    # basic config
    level: int = 0

    # visual stimulation config
    stimulation_size: int = 0

    # audio stimulation config
    stimulus_duration: int = 0

    # trial lifecycle
    time_out: int = 0
    inter_trial_interval: int = 0

    # reward config
    reward_duration: int = 0
    reward_delay: int = 0


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
