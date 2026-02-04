from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, Field
from pymxbi.detector import DetectorEnum
from pymxbi.platform import PlatformEnum
from pymxbi.rewarder import RewarderEnum


class MockRewarderModel(BaseModel):
    type: Literal[RewarderEnum.MOCK] = RewarderEnum.MOCK
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.type)


class GPIORewarderModel(BaseModel):
    type: Literal[RewarderEnum.RPI_GPIO] = RewarderEnum.RPI_GPIO
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=13, ge=0)

    @property
    def device_type(self) -> str:
        return str(self.type)


RewarderModel: TypeAlias = Annotated[
    Union[GPIORewarderModel, MockRewarderModel],
    Field(discriminator="type"),
]


class MockDetectorModel(BaseModel):
    type: Literal[DetectorEnum.MOCK] = DetectorEnum.MOCK
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.type)


class RFIDContinuousDetectorModel(BaseModel):
    type: Literal[DetectorEnum.RFID_CONTINUOUS] = DetectorEnum.RFID_CONTINUOUS
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    port: str = Field(default="/dev/ttyUSB0")
    baudrate: int = Field(default=9600, ge=1)

    @property
    def device_type(self) -> str:
        return str(self.type)


class BeamBreakContinuousDetectorModel(BaseModel):
    type: Literal[DetectorEnum.BEAMBREAK_CONTINUOUS] = DetectorEnum.BEAMBREAK_CONTINUOUS
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=17, ge=0)

    @property
    def device_type(self) -> str:
        return str(self.type)


class FusionContinuousDetectorModel(BaseModel):
    type: Literal[DetectorEnum.FUSION_CONTINUOUS] = DetectorEnum.FUSION_CONTINUOUS
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=17, ge=0)
    port: str = Field(default="/dev/ttyUSB0")
    baudrate: int = Field(default=9600, ge=1)

    @property
    def device_type(self) -> str:
        return str(self.type)


DetectorModel: TypeAlias = Annotated[
    Union[
        MockDetectorModel,
        RFIDContinuousDetectorModel,
        BeamBreakContinuousDetectorModel,
        FusionContinuousDetectorModel,
    ],
    Field(discriminator="type"),
]


class MXBIModel(BaseModel):
    mxbi_id: int = Field(default=0, ge=0)
    platform: PlatformEnum = Field(default=PlatformEnum.RASPBIAN)
    screen_size: tuple[int, int] = Field(default=(1024, 600))
    rewarders: list[RewarderModel] = Field(default_factory=list)
    detectors: list[DetectorModel] = Field(default_factory=list)
