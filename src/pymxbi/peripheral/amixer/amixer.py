"""Helpers for controlling audio volume via `amixer`."""

import subprocess


def set_master_volume(volume: int) -> None:
    """Set the ALSA `Master` volume.

    Parameters
    ----------
    volume : int
        Volume percentage (0-100).
    """
    subprocess.run(["amixer", "sset", "Master", f"{volume}%"])


def set_digital_volume(volume: int) -> None:
    """Set the ALSA `Digital` volume on card 0.

    Parameters
    ----------
    volume : int
        Volume value passed to `amixer` (commonly 0-100 for percent-based controls).
    """
    subprocess.run(["amixer", "-c", "0", "sset", "Digital", f"{volume}"])
