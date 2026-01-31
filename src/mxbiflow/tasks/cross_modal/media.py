import wave
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from mxbi.utils.aplayer import SAMPLE_RATE


def load_wav_as_int16(
    path: Path,
    *,
    target_rate: int = SAMPLE_RATE,
    rate_policy: Literal["resample", "error"] = "resample",
    gain: float = 1.0,
) -> NDArray[np.int16]:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        sample_width = wf.getsampwidth()
        channel_count = wf.getnchannels()
        source_rate = wf.getframerate()

    if sample_width != 2:
        raise ValueError(f"Only 16-bit WAVs supported, got sampwidth={sample_width}")

    data = np.frombuffer(frames, dtype=np.int16)

    if channel_count > 1:
        data = data.reshape(-1, channel_count).mean(axis=1).astype(np.int16)

    float_data = (data.astype(np.float32)) / float(np.iinfo(np.int16).max)

    if source_rate != target_rate:
        if rate_policy == "error":
            raise ValueError(
                f"WAV sample rate mismatch: wav={source_rate}Hz, expected={target_rate}Hz"
            )
        float_data = _resample_1d(float_data, source_rate=source_rate, target_rate=target_rate)

    if gain != 1.0:
        float_data = np.clip(float_data * gain, -1.0, 1.0)

    return (float_data * float(np.iinfo(np.int16).max)).astype(np.int16)


def _resample_1d(
    signal: NDArray[np.float32], *, source_rate: int, target_rate: int
) -> NDArray[np.float32]:
    if signal.size == 0:
        return signal

    target_length = int(round(signal.size * (target_rate / source_rate)))
    if target_length <= 0:
        return np.zeros(0, dtype=np.float32)

    old_positions = np.linspace(0.0, 1.0, num=signal.size, endpoint=False)
    new_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    resampled = np.interp(new_positions, old_positions, signal).astype(np.float32)
    return resampled
