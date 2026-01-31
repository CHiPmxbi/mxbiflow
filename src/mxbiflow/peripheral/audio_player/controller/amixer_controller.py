import subprocess

from mxbi.peripheral.audio_player.controller.config import digital_values, master_values


class AmixerController:
    def set_master_volume(self, volume: int) -> None:
        subprocess.run(["amixer", "sset", "Master", f"{volume}%"])

    def set_digital_volume(self, volume: int) -> None:
        subprocess.run(["amixer", "-c", "0", "sset", "Digital", f"{volume}"])

    def get_amp_value(self, freqency: int, amplitude: float) -> tuple[int, int]:
        return master_values[freqency], digital_values[amplitude]
