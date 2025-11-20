from enum import StrEnum, auto

from pydantic import BaseModel


class Result(StrEnum):
    CORRECT = auto()
    INCORRECT = auto()


class TrialConfig(BaseModel):
    level: int
    entry_reward: bool

    min_stimulus_interval: float  # seconds
    max_stimulus_interval: float  # seconds
    target: float  # seconds

    reward_duration: int = 1000  # milliseconds
    stimulus_duration: int = 1000  # milliseconds

    stimulus_density: int  # volume 0-100

    stimulus_freq: int = 2000
    stimulus_freq_duration: int = 100
    stimulus_freq_interval: int = 100


class TrialData(BaseModel):
    level: int
    animal: str
    trial_id: int
    level_trial_id: int
    animal_session_trial_id: int
    trial_start_time: float
    trial_end_time: float
    result: Result

    stay_duration: float


class DataToShow(BaseModel):
    level: int
    name: str
    id: int
    lid: int
    ald: int
    t_dur: str
    dur: str
    rewards: int
