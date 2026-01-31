from enum import StrEnum, auto

from mxbi.peripheral.audio_player.controller.amixer_controller import AmixerController
from mxbi.peripheral.audio_player.controller.controller import Controller
from mxbi.peripheral.audio_player.controller.mock_controller import MockController


class AudioControllerEnum(StrEnum):
    MOCK = auto()
    AMIXER = auto()


DEFAULT_PUMP = AudioControllerEnum.AMIXER


class AudioControllerFactory:
    """Factory responsible for creating rewarder instances."""

    pumps: dict[AudioControllerEnum, type[Controller]] = {
        AudioControllerEnum.MOCK: MockController,
        AudioControllerEnum.AMIXER: AmixerController,
    }

    @classmethod
    def create(cls, rewarder_type: AudioControllerEnum) -> Controller:
        try:
            rewarder_cls = cls.pumps[rewarder_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported rewarder type: {rewarder_type}") from exc
        return rewarder_cls()
