from pydantic import BaseModel, Field
from .animal import Animals, AnimalConfig

from .reward import RewardEnum


class SessionConfig(BaseModel):
    experimenter: str = Field(default="auto", frozen=True)
    reward_type: RewardEnum = Field(default=RewardEnum.AGUM_ONE_FIFTH, frozen=True)

    animals: list[AnimalConfig] = Field(default_factory=list)


class SessionState(BaseModel):
    session_id: int = Field(frozen=True)
    start_at: float = Field(frozen=True)
    end_at: float = Field(frozen=True)
    note: str = Field(frozen=True)

    animals: Animals = Field(frozen=True)


class Session(BaseModel):
    config: SessionConfig
    state: SessionState

class Options(BaseModel):
    mxbis: list[str] = Field(default_factory=list, frozen=True)
    experimenter: list[str] = Field(default_factory=list, frozen=True)
    animals: dict[str, str] = Field(default_factory=dict, frozen=True)
