from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel

from mxbi.config import Configure
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.GNGSiD.models import LevelID, MonkeyName

CONFIG_PATH = Path(__file__).parent / "config.json"


class SizeReductionStageParameters(BaseModel):
    model_config = ConfigDict(frozen=True)

    # audio stimulation config
    stimulus_duration: int
    stimulus_freq: int
    stimulus_freq_duration: int
    stimulus_interval: int

    # trial lifecycle
    time_out: int
    inter_trial_interval: int

    # reward config
    reward_duration: int


class SizeReductionStageLeveledParameters(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int
    stimulation_size: int
    reward_delay: int


class SizeReductionStageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: ScheduleCondition

    params: SizeReductionStageParameters
    levels_table: dict[LevelID, SizeReductionStageLeveledParameters]


class SizeReductionStageConfigs(RootModel):
    model_config = ConfigDict(frozen=True)

    root: dict[MonkeyName, SizeReductionStageConfig]


def load_config() -> SizeReductionStageConfigs:
    configs = Configure(CONFIG_PATH, SizeReductionStageConfigs).value
    for config in configs.root.values():
        config.condition.level_count = len(config.levels_table)
    return configs


config = load_config()
