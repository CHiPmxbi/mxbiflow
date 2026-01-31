from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, RootModel

from mxbi.config import Configure
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.GNGSiD.models import LevelID, MonkeyName

CONFIG_PATH: Path = Path(__file__).parent / "config.json"


class StimulusConfig(BaseModel):
    stimulus_freq_high: int
    stimulus_freq_high_duration: int
    stimulus_freq_low: int
    stimulus_freq_low_duration: int


class DiscriminateStageParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # visual stimulation config
    stimulation_size: int
    visual_stimulus_delay: int

    # dynamic reward config
    medium_reward_duration: int
    medium_reward_threshold: int
    low_reward_duration: int

    # audio stimulation config
    min_stimulus_duration: int
    max_stimulus_duration: int
    stimulus_configs: List[StimulusConfig]
    stimulus_interval: int
    extra_response_time: int

    # trial lifecycle
    time_out: int
    inter_trial_interval: int

    # reward config
    reward_duration: int
    reward_delay: int

    attention_duration: int


class DiscriminateStageLeveledParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int

    stimulus_trial_prob: float
    nostimulus_trial_prob: float


class DiscriminateStageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: ScheduleCondition

    params: DiscriminateStageParams
    levels_table: Dict[LevelID, DiscriminateStageLeveledParams]


class DiscriminateStageConfigs(RootModel):
    model_config = ConfigDict(frozen=True)

    root: Dict[MonkeyName, DiscriminateStageConfig]


def load_config() -> DiscriminateStageConfigs:
    configs = Configure(CONFIG_PATH, DiscriminateStageConfigs).value
    for config in configs.root.values():
        config.condition.level_count = len(config.levels_table)
    return configs


config = load_config()
