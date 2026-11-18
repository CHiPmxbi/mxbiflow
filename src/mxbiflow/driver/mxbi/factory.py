from typing import Annotated, Literal

from py_mx_eye import MxEye, MxEyeConfig
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..audioplayer import AudioPlayer
from ..audioplayer.frequency_response_table import FrequencyResponseTable
from ..channels import (
    DetectorInput,
    GpioInput,
    GpioOutput,
    InputChannel,
    OutputChannel,
    RewarderOutput,
)
from ..detector import (
    BeambreakContinuousDetector,
    Detector,
    DetectorEnum,
    DetectorModel,
    FusionContinuousDetector,
    MockDetector,
    RFIDContinuousDetector,
)
from ..eyetracker import (
    Eyetracker,
    EyetrackerEnum,
    EyetrackerModel,
    MockEyetracker,
    MxEyeEyetracker,
)
from ..peripheral.beam_break_sensor import RPIIRBreakBeamSensor
from ..peripheral.rfid import DorsetLID665v42
from ..rewarder import (
    MockRewarder,
    Rewarder,
    RewarderEnum,
    RewarderModel,
    RPIGpioRewarder,
)
from .mxbi import MXBI


class DetectorInputModel(BaseModel):
    """High while the detector sees an animal."""

    model_config = ConfigDict(title="Detector")

    type: Literal["detector"] = "detector"
    id: int = Field(default=0, ge=0, title="Detector id")


class GpioInputModel(BaseModel):
    """A GPIO pin, such as a lick port or a photodiode; its edges are timed."""

    model_config = ConfigDict(title="GPIO pin")

    type: Literal["gpio"] = "gpio"
    pin: int = Field(ge=0)
    pull_up: bool | None = Field(
        default=False,
        title="Pull-up",
        description=(
            "Internal resistor: pull-up (the input is high when the pin is low), "
            "pull-down (high when the pin is high), or none with active_high set"
        ),
    )
    active_high: bool | None = Field(
        default=None,
        title="Active high",
        description="Which pin level is high; only for a pin without a resistor",
    )
    bounce_ms: int | None = Field(
        default=None,
        gt=0,
        title="Debounce (ms)",
        description="Ignore changes that follow one within this time",
    )

    @model_validator(mode="after")
    def _validate_active_state(self) -> GpioInputModel:
        if (self.pull_up is None) != (self.active_high is not None):
            raise ValueError("set active_high exactly when pull_up is null")
        return self


class RewarderOutputModel(BaseModel):
    """The rewarder runs while the output is high."""

    model_config = ConfigDict(title="Rewarder")

    type: Literal["rewarder"] = "rewarder"
    id: int = Field(default=0, ge=0, title="Rewarder id")


class GpioOutputModel(BaseModel):
    """A GPIO pin driven high while the output is high."""

    model_config = ConfigDict(title="GPIO pin")

    type: Literal["gpio"] = "gpio"
    pin: int = Field(ge=0)
    active_high: bool = Field(default=True, title="Active high")


type InputChannelModel = Annotated[
    DetectorInputModel | GpioInputModel, Field(discriminator="type")
]
type OutputChannelModel = Annotated[
    RewarderOutputModel | GpioOutputModel, Field(discriminator="type")
]


class ChannelsModel(BaseModel):
    """The wiring of state machines' channels (:mod:`mxbiflow.statemachine`) on this rig.

    A machine names its inputs and outputs; the rig says what each name is wired to.
    """

    model_config = ConfigDict(title="State machine channels")

    inputs: dict[str, InputChannelModel] = Field(default_factory=dict, title="Inputs")
    outputs: dict[str, OutputChannelModel] = Field(
        default_factory=dict, title="Outputs"
    )


class AudioModel(BaseModel):
    """The audio output every sound is played on, in one format."""

    model_config = ConfigDict(title="Audio output")

    sample_rate_hz: int | None = Field(
        default=None,
        gt=0,
        title="Sample rate",
        description="Sounds are converted to it when loaded; empty is the device's own",
    )
    channels: int = Field(default=2, gt=0, title="Channels")


class MXBIModel(BaseModel):
    """The rig hardware; the device name in cogmote identifies the rig."""

    screen_size: tuple[int, int] = Field(default=(1024, 600), title="Screen size")
    rewarders: list[RewarderModel] = Field(default_factory=list, title="Rewarders")
    detectors: list[DetectorModel] = Field(default_factory=list, title="Detectors")
    eyetrackers: list[EyetrackerModel] = Field(
        default_factory=list, title="Eye trackers"
    )
    frequency_response_table: dict[int, Annotated[int, Field(ge=0, le=100)]] = Field(
        default_factory=dict,
        title="Frequency response table",
        description="Master volume for each tone frequency, for this rig's speaker",
        json_schema_extra={
            "propertyNames": {"pattern": "^[1-9][0-9]*$"},
            "x-mxbi-columns": ["Frequency (Hz)", "Master volume (%)"],
        },
    )
    audio: AudioModel = Field(default_factory=AudioModel)
    channels: ChannelsModel = Field(default_factory=ChannelsModel)


def build_mxbi(config: MXBIModel, logger=None) -> MXBI:
    rewarders = _build_rewarders(config.rewarders, logger)
    detectors = _build_detectors(config.detectors)
    return MXBI(
        config.screen_size,
        rewarders,
        detectors,
        _build_eyetrackers(config.eyetrackers),
        aplayer=AudioPlayer(
            sample_rate_hz=config.audio.sample_rate_hz,
            channels=config.audio.channels,
            # An empty table is no table: stages test for None before looking up a
            # volume.
            frequency_response_table=FrequencyResponseTable(
                config.frequency_response_table
            )
            if config.frequency_response_table
            else None,
        ),
        inputs={
            name: _make_input(name, wire, detectors)
            for name, wire in config.channels.inputs.items()
        },
        outputs={
            name: _make_output(name, wire, rewarders)
            for name, wire in config.channels.outputs.items()
        },
    )


def _make_input(
    name: str, wire: InputChannelModel, detectors: dict[int, Detector]
) -> InputChannel:
    if isinstance(wire, GpioInputModel):
        return GpioInput(
            wire.pin,
            pull_up=wire.pull_up,
            active_high=wire.active_high,
            bounce_s=wire.bounce_ms / 1000 if wire.bounce_ms else None,
        )
    if wire.id not in detectors:
        raise ValueError(f'input "{name}" is wired to detector {wire.id}, not enabled')
    return DetectorInput(detectors[wire.id])


def _make_output(
    name: str, wire: OutputChannelModel, rewarders: dict[int, Rewarder]
) -> OutputChannel:
    if isinstance(wire, GpioOutputModel):
        return GpioOutput(wire.pin, active_high=wire.active_high)
    if wire.id not in rewarders:
        raise ValueError(f'output "{name}" is wired to rewarder {wire.id}, not enabled')
    return RewarderOutput(rewarders[wire.id])


def _build_rewarders(
    configs: list[RewarderModel],
    logger=None,
) -> dict[int, Rewarder]:

    enabled = [c for c in configs if c.enabled]
    if not enabled:
        raise ValueError("No rewarders configured")

    rewarders = {c.id: _make_rewarder(c, logger) for c in enabled}
    return rewarders


def _make_rewarder(config: RewarderModel, logger=None) -> Rewarder:
    match config.type:
        case RewarderEnum.MOCK:
            return MockRewarder(logger)

        case RewarderEnum.RPI_GPIO:
            return RPIGpioRewarder(config.pin)

        case _:
            raise ValueError(f"Unknown rewarder type: {config.type}")


def _build_detectors(configs: list[DetectorModel]) -> dict[int, Detector]:
    enabled = [c for c in configs if c.enabled]
    if not enabled:
        raise ValueError("No detectors configured")

    detectors = {c.id: _make_detector(c) for c in enabled}
    return detectors


def _make_detector(config: DetectorModel) -> Detector:
    match config.type:
        case DetectorEnum.MOCK:
            return MockDetector()

        case DetectorEnum.RFID_CONTINUOUS:
            rfid_reader = DorsetLID665v42(config.port, config.baudrate)
            return RFIDContinuousDetector(rfid_reader)

        case DetectorEnum.BEAMBREAK_CONTINUOUS:
            sensor = RPIIRBreakBeamSensor(config.pin)
            return BeambreakContinuousDetector(sensor)

        case DetectorEnum.FUSION_CONTINUOUS:
            rfid_reader = DorsetLID665v42(config.port, config.baudrate)
            sensor = RPIIRBreakBeamSensor(config.pin)
            return FusionContinuousDetector(
                rfid_reader,
                sensor,
                poll_interval=config.poll_interval,
                rfid_timeout=config.rfid_timeout,
                beam_break_filter_enabled=config.beam_break_filter_enabled,
                beam_break_filter_duration=config.beam_break_filter_duration,
            )

        case _:
            raise ValueError(f"Unknown detector type: {config.type}")


def _build_eyetrackers(configs: list[EyetrackerModel]) -> dict[int, Eyetracker]:
    return {c.id: _make_eyetracker(c) for c in configs if c.enabled}


def _make_eyetracker(config: EyetrackerModel) -> Eyetracker:
    match config.type:
        case EyetrackerEnum.MOCK:
            return MockEyetracker()

        case EyetrackerEnum.MX_EYE:
            client = MxEye(
                MxEyeConfig(
                    host=config.host,
                    data_port=config.data_port,
                    control_port=config.control_port,
                    timeout=config.timeout,
                )
            )
            return MxEyeEyetracker(
                client,
                poll_timeout=config.poll_timeout,
                max_age_ms=config.max_age_ms,
                start_acquisition=config.start_acquisition,
            )

        case _:
            raise ValueError(f"Unknown eyetracker type: {config.type}")
