from enum import StrEnum, auto

from pydantic import BaseModel, ConfigDict, Field

from mxbi.models.animal import AnimalConfig, AnimalOptions
from mxbi.models.detector import DetectorEnum
from mxbi.models.reward import RewardEnum
from mxbi.peripheral.pumps.pump_factory import DEFAULT_PUMP, PumpEnum
from mxbi.utils.detect_platform import PlatformEnum


class ScreenTypeEnum(StrEnum):
    DEFAULT = auto()


class ScreenConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: ScreenTypeEnum = ScreenTypeEnum.DEFAULT
    width: int = 1024
    height: int = 600


class SessionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    experimenter: str = ""
    xbi_id: str = ""
    comments: str = ""
    reward_type: RewardEnum = RewardEnum.AGUM_ONE_FIFTH
    pump_type: PumpEnum = DEFAULT_PUMP
    platform: PlatformEnum = PlatformEnum.RASPBERRY
    detector: DetectorEnum = DetectorEnum.MOCK
    detector_port: str | None = None
    detector_baudrate: int | None = None
    detector_interval: float | None = None
    screen_type: ScreenConfig = Field(default_factory=ScreenConfig)
    animals: dict[str, AnimalConfig] = Field(default_factory=dict)

    # Cross-modal recognition specific configuration
    cross_modal_trial_file: str | None = None
    cross_modal_media_root: str | None = None


class SessionState(BaseModel):
    session_id: int = 0
    start_time: float = Field(default=0.0, frozen=True)
    end_time: float = 0.0

    session_config: SessionConfig = Field(default_factory=SessionConfig, frozen=True)


class SessionOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    experimenter: list[str]
    xbi_id: list[str]
    reward_type: list[RewardEnum] = Field(default_factory=lambda: list(RewardEnum))
    pump_type: list[PumpEnum] = Field(default_factory=lambda: list(PumpEnum))
    platform: list[PlatformEnum] = Field(default_factory=lambda: list(PlatformEnum))
    detecotr: list[DetectorEnum] = Field(default_factory=lambda: list(DetectorEnum))
    detector_baudrates: list[int] = Field(
        default_factory=lambda: [9600, 19200, 38400, 57600, 115200]
    )
    screen_type: dict[ScreenTypeEnum, ScreenConfig] = Field(
        default_factory=lambda: dict({ScreenTypeEnum.DEFAULT: ScreenConfig()})
    )
    animal: AnimalOptions
