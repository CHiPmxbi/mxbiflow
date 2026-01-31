from mxbi.peripheral.audio_player.controller.config import digital_values, master_values
from mxbi.utils.logger import logger


class MockController:
    def set_master_volume(self, volume: int) -> None:
        logger.info(f"Set master volume to {volume}")

    def set_digital_volume(self, volume: int) -> None:
        logger.info(f"Set digital volume to {volume}")

    def get_amp_value(self, freqency: int, amplitude: float) -> tuple[int, int]:
        return master_values[freqency], digital_values[amplitude]
