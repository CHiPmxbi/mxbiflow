import subprocess


def set_master_volume(volume: int) -> None:
    subprocess.run(["amixer", "sset", "Master", f"{volume}%"])


def set_digital_volume(volume: int) -> None:
    subprocess.run(["amixer", "-c", "0", "sset", "Digital", f"{volume}"])
