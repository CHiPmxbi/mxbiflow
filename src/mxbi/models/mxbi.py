from __future__ import annotations

from enum import StrEnum, auto
from typing import Annotated, Union, TypeAlias, Literal

from pydantic import BaseModel, Field


class RewarderTypeEnum(StrEnum):
    MOCK_REWARDER = auto()
    GPIO_REWARDER = auto()


class DetectorTypeEnum(StrEnum):
    MOCK_DETECTOR = auto()
    RFID_DETECTOR = auto()
    BEAM_RFID_DETECTOR = auto()


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


class BeamRFIDDetectorModel(BaseModel):
    detector_type: Literal[DetectorTypeEnum.BEAM_RFID_DETECTOR] = (
        DetectorTypeEnum.BEAM_RFID_DETECTOR
    )
    detector_id: int = Field(default=0, ge=0)
    beam_break_pin: int = Field(default=17, ge=0)
    rfid_reader_port: str = Field(default="/dev/ttyUSB0")
    rfid_baudrate: int = Field(default=9600, ge=1)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


class RFIDDetectorModel(BaseModel):
    detector_type: Literal[DetectorTypeEnum.RFID_DETECTOR] = (
        DetectorTypeEnum.RFID_DETECTOR
    )
    detector_id: int = Field(default=0, ge=0)
    port: str = Field(default="/dev/ttyUSB0")
    baudrate: int = Field(default=9600, ge=1)
    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


class MockDetectorModel(BaseModel):
    detector_type: Literal[DetectorTypeEnum.MOCK_DETECTOR] = (
        DetectorTypeEnum.MOCK_DETECTOR
    )
    detector_id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.detector_type)


DetectorModel: TypeAlias = Annotated[
    Union[RFIDDetectorModel, BeamRFIDDetectorModel, MockDetectorModel],
    Field(discriminator="detector_type"),
]


class MXBIModel(BaseModel):
    mxbi_id: int = Field(default=0, ge=0)
    platform: MXBIPlatformEnum = Field(default=MXBIPlatformEnum.RASPBIAN)
    rewarders: list[RewarderModel] = Field(default_factory=list)
    detectors: list[DetectorModel] = Field(default_factory=list)
