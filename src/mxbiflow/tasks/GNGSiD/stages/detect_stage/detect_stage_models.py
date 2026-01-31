from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel

from mxbi.config import Configure
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.GNGSiD.models import LevelID, MonkeyName

CONFIG_PATH = Path(__file__).parent / "config.json"


class DetectStageParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # visual stimulation config
    stimulation_size: int
    visual_stimulus_delay: int

    # audio stimulation config
    stimulus_freq: int
    stimulus_freq_duration: int
    stimulus_interval: int

    # trial lifecycle
    time_out: int
    inter_trial_interval: int

    # reward config
    reward_duration: int
    reward_delay: int


class DetectStageLeveledParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int
    min_stimulus_duration: int
    max_stimulus_duration: int

    go_task_prob: float
    nogo_task_prob: float


class DetectStageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: ScheduleCondition

    params: DetectStageParams
    levels_table: dict[LevelID, DetectStageLeveledParams]


class DetectStageConfigs(RootModel):
    model_config = ConfigDict(frozen=True)

    root: dict[MonkeyName, DetectStageConfig]


def load_config() -> DetectStageConfigs:
    configs = Configure(CONFIG_PATH, DetectStageConfigs).value
    for config in configs.root.values():
        config.condition.level_count = len(config.levels_table)
    return configs


config = load_config()
