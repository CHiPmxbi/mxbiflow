from __future__ import annotations

from enum import StrEnum, auto
from typing import Annotated, Union, TypeAlias, Literal

from pydantic import BaseModel, Field
from pymxbi.detector import DetectorType


class RewarderTypeEnum(StrEnum):
    MOCK_REWARDER = auto()
    GPIO_REWARDER = auto()


class MXBIPlatformEnum(StrEnum):
    RASPBIAN = auto()
    UBUNTU = auto()
    WINDOWS = auto()
    MACOS = auto()


class MockRewarderModel(BaseModel):
    rewarder_type: Literal[RewarderTypeEnum.MOCK_REWARDER] = (
        RewarderTypeEnum.MOCK_REWARDER
    )
    rewarder_id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.rewarder_type)


class GPIORewarderModel(BaseModel):
    rewarder_type: Literal[RewarderTypeEnum.GPIO_REWARDER] = (
        RewarderTypeEnum.GPIO_REWARDER
    )
    rewarder_id: int = Field(default=0, ge=0)
    pin: int = Field(default=13, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.rewarder_type)


RewarderModel: TypeAlias = Annotated[
    Union[GPIORewarderModel, MockRewarderModel],
    Field(discriminator="rewarder_type"),
]


class MockDetectorModel(BaseModel):
    detector_type: Literal[DetectorType.MOCK] = DetectorType.MOCK
    detector_id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


class RFIDContinuousDetectorModel(BaseModel):
    detector_type: Literal[DetectorType.RFID_CONTINUOUS] = DetectorType.RFID_CONTINUOUS
    detector_id: int = Field(default=0, ge=0)

    enabled: bool = False

    port: str = Field(default="/dev/ttyUSB0")
    baudrate: int = Field(default=9600, ge=1)

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


class BeamBreakContinuousDetectorModel(BaseModel):
    detector_type: Literal[DetectorType.BEAMBREAK_CONTINUOUS] = (
        DetectorType.BEAMBREAK_CONTINUOUS
    )
    detector_id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=17, ge=0)

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


class FusionContinuousDetectorModel(BaseModel):
    detector_type: Literal[DetectorType.FUSION_CONTINUOUS] = (
        DetectorType.FUSION_CONTINUOUS
    )
    detector_id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=17, ge=0)
    port: str = Field(default="/dev/ttyUSB0")
    baudrate: int = Field(default=9600, ge=1)

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


DetectorModel: TypeAlias = Annotated[
    Union[
        MockDetectorModel,
        RFIDContinuousDetectorModel,
        BeamBreakContinuousDetectorModel,
        FusionContinuousDetectorModel,
    ],
    Field(discriminator="detector_type"),
]


class MXBIModel(BaseModel):
    mxbi_id: int = Field(default=0, ge=0)
    platform: MXBIPlatformEnum = Field(default=MXBIPlatformEnum.RASPBIAN)
    screen_size: tuple[int, int] = Field(default=(1920, 1080))
    rewarders: list[RewarderModel] = Field(default_factory=list)
    detectors: list[DetectorModel] = Field(default_factory=list)
