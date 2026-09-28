from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .eyetracker import EyeSample, Eyetracker, EyetrackerEnum
from .mock_eyetracker import MockEyetracker
from .mx_eye_eyetracker import MxEyeEyetracker


class MxEyeEyetrackerModel(BaseModel):
    type: Literal[EyetrackerEnum.MX_EYE] = EyetrackerEnum.MX_EYE
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    host: str = "127.0.0.1"
    data_port: int = Field(default=5556, ge=1, le=65535)
    control_port: int = Field(default=5557, ge=1, le=65535)
    timeout: float = Field(default=3.0, gt=0)
    poll_timeout: float = Field(default=0.1, gt=0)
    max_age_ms: float = Field(default=50.0, gt=0)
    start_acquisition: bool = False

    @property
    def device_type(self) -> str:
        return str(self.type)


class MockEyetrackerModel(BaseModel):
    type: Literal[EyetrackerEnum.MOCK] = EyetrackerEnum.MOCK
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.type)


type EyetrackerModel = Annotated[
    MxEyeEyetrackerModel | MockEyetrackerModel,
    Field(discriminator="type"),
]


__all__ = [
    "EyeSample",
    "Eyetracker",
    "EyetrackerEnum",
    "EyetrackerModel",
    "MockEyetracker",
    "MockEyetrackerModel",
    "MxEyeEyetracker",
    "MxEyeEyetrackerModel",
]
