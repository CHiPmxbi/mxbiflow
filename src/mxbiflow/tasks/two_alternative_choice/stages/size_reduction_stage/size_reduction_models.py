from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel

from mxbi.config import Configure
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.two_alternative_choice.models import LevelID, MonkeyName
from mxbi.tasks.two_alternative_choice.tasks.touch.touch_models import TrialConfig

CONFIG_PATH = Path(__file__).parent / "config.json"


class SizeReductionStageLeveledParameters(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: int
    stimulation_size: int


class SizeReductionStageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: ScheduleCondition
    trial_config: TrialConfig

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
