from pydantic import BaseModel, ConfigDict, Field, RootModel
from enum import StrEnum, auto
from pathlib import Path
from mxbiflow.models.animal import AnimalBaseInfo
import json

CONFIG_PATH = Path(__file__).parent / "config.json"


class Result(StrEnum):
    CORRECT = auto()
    INCORRECT = auto()
    TIMEOUT = auto()
    CANCELLED = auto()


class HabituationResult(BaseModel):
    animals: list[AnimalBaseInfo]

    result: Result

    trial_start_time: float
    trial_end_time: float
    stay_duration: float

    def save(self, path: Path):
        json_data = self.model_dump_json()
        with path.open("a") as f:
            f.write(json_data + "\n")


class HabituationConfig(BaseModel):
    level: int = Field(ge=0)
    entry_reward: float = Field(ge=0)

    evaluation_interval: int = Field(ge=0)

    min_stimulus_interval: int = Field(ge=0)
    max_stimulus_interval: int = Field(ge=0)
    stimulus_interval: int = Field(default=0, ge=0, exclude=True)

    target: int = Field(ge=0)

    reward_dutration: int = Field(ge=0)

    stimulus_density: int = Field(ge=0, le=100)


class HabituationConfigs(RootModel[dict[str, dict[int, HabituationConfig]]]):
    model_config = ConfigDict(frozen=True)


def load_configs() -> HabituationConfigs:
    with CONFIG_PATH.open("r") as f:
        config = json.load(f)
        return HabituationConfigs.model_validate(config)
