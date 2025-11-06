from pydantic import BaseModel
from enum import StrEnum, auto


class Result(StrEnum):
    CORRECT = auto()
    INCORRECT = auto()


class TrialConfig(BaseModel):
    level: int = 0
    reward_interval: int = 0
    reward_duration: int = 0
    stimulus_duration: int = 0
    stimulus_density: int = 0

    stimulus_freq: int = 2000
    stimulus_freq_duration: int = 100
    stimulus_freq_interval: int = 100


class TrialData(BaseModel):
    animal: str
    trial_id: int
    trial_start_time: float
    trial_end_time: float
    result: Result

    stay_duration: float


class DataToShow(BaseModel):
    level: int
    name: str
    id: int
    t_dur: str
    dur: str
    rewards: int
