from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel, Field

from mxbi.config import Configure
from mxbi.tasks.GNGSiD.models import MonkeyName
from mxbi.models.animal import ScheduleCondition

CONFIG_PATH = Path(__file__).parent / "config.json"


class InitialHabituationTraingStageLeveledParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_interval: int

    level: int
    reward_interval: int
    reward_duration: int

    stimulus_duration: int
    stimulus_density: int


class InitialHabituationTrainingStageConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    condition: ScheduleCondition
    levels_table: dict[int, InitialHabituationTraingStageLeveledParams]


class InitialHabituationTrainingStageConfigs(RootModel):
    model_config = ConfigDict(frozen=True)

    root: dict[MonkeyName, InitialHabituationTrainingStageConfig]


class StageContext(BaseModel):
    duration: int = 0
    rewards: int = 0


class StageContexts(RootModel):
    root: dict[MonkeyName, StageContext] = Field(default_factory=dict)


def load_config() -> InitialHabituationTrainingStageConfigs:
    configs = Configure(CONFIG_PATH, InitialHabituationTrainingStageConfigs).value
    for config in configs.root.values():
        config.condition.level_count = len(config.levels_table)
    return configs


config = load_config()
