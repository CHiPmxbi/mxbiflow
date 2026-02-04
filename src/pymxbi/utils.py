from pydantic import BaseModel, Field
from .mxbi import MXBI
from .platform import PlatformEnum
from .rewarder import (
    RewarderModel,
    Rewarder,
    RewarderEnum,
    MockRewarder,
    RPIGpioRewarder,
)
from .detector import (
    DetectorModel,
    Detector,
    DetectorEnum,
    MockDetector,
    RFIDContinuousDetector,
    BeambreakContinuousDetector,
    FusionContinuousDetector,
)
from .peripheral.rfid import DorsetLID665v42
from .peripheral.beam_break_sensor import RPIIRBreakBeamSensor


class MXBIModel(BaseModel):
    mxbi_id: int = Field(default=0, ge=0)
    platform: PlatformEnum = Field(default=PlatformEnum.RASPBIAN)
    screen_size: tuple[int, int] = Field(default=(1024, 600))
    rewarders: list[RewarderModel] = Field(default_factory=list)
    detectors: list[DetectorModel] = Field(default_factory=list)


def build_mxbi(config: MXBIModel, logger=None) -> MXBI:
    return MXBI(
        config.screen_size,
        _build_rewarders(config.rewarders),
        _build_detectors(config.detectors),
    )


def _build_rewarders(configs: list[RewarderModel], logger=None) -> dict[int, Rewarder]:
    rewarders: dict[int, Rewarder] = {}
    for config in configs:
        match config.type:
            case RewarderEnum.MOCK:
                rewarder = MockRewarder(logger)
                rewarders[config.id] = rewarder
            case RewarderEnum.RPI_GPIO:
                rewarder = RPIGpioRewarder(config.pin)
                rewarders[config.id] = rewarder
            case _:
                raise ValueError(f"Unknown rewarder type: {config.type}")

    if not rewarders:
        raise ValueError("No rewarders configured")

    return rewarders


def _build_detectors(configs: list[DetectorModel]) -> dict[int, Detector]:
    detectors: dict[int, Detector] = {}
    for config in configs:
        match config.type:
            case DetectorEnum.MOCK:
                detector = MockDetector()
                detectors[config.id] = detector
            case DetectorEnum.RFID_CONTINUOUS:
                rfid_reader = DorsetLID665v42(config.port, config.baudrate)
                detector = RFIDContinuousDetector(rfid_reader)
                detectors[config.id] = detector
            case DetectorEnum.BEAMBREAK_CONTINUOUS:
                sensor = RPIIRBreakBeamSensor(config.pin)
                detector = BeambreakContinuousDetector(sensor)
                detectors[config.id] = detector
            case DetectorEnum.FUSION_CONTINUOUS:
                rfid_reader = DorsetLID665v42(config.port, config.baudrate)
                sensor = RPIIRBreakBeamSensor(config.pin)
                detector = FusionContinuousDetector(rfid_reader, sensor)
                detectors[config.id] = detector
            case _:
                raise ValueError(f"Unknown detector type: {config.type}")

    if not detectors:
        raise ValueError("No detectors configured")

    return detectors
