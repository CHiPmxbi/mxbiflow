import wave
from pathlib import Path
import numpy as np
from numpy.typing import NDArray


def load_wav_as_int16(path: Path) -> NDArray[np.int16]:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        sampwidth = wf.getsampwidth()
        n_channels = wf.getnchannels()
        if sampwidth != 2:
            raise ValueError(f"Only 16-bit WAVs supported, got sampwidth={sampwidth}")
        data = np.frombuffer(frames, dtype=np.int16)
        if n_channels > 1:
            data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
    return data