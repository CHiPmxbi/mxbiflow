"""Sounds as samples, wherever they come from: a file, tones.

A :class:`Sound` is what the audio player plays. A file's or a tone train's sound is
in its own format; :func:`convert` brings it to the output's, once, before it is played.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import soundfile
import soxr
from numpy.typing import NDArray

from .puretone_generator import PureToneUnit


@dataclass(frozen=True)
class AudioFormat:
    sample_rate_hz: int
    channels: int


@dataclass(frozen=True, eq=False)
class Sound:
    #: Frames by channels, each sample from -1 to 1.
    samples: NDArray[np.float32]
    sample_rate_hz: int

    def __post_init__(self) -> None:
        if self.samples.ndim != 2 or self.samples.dtype != np.float32:
            raise ValueError("a sound's samples are float32, frames by channels")
        if self.sample_rate_hz <= 0:
            raise ValueError(f"sample rate {self.sample_rate_hz} Hz is not positive")

    @property
    def format(self) -> AudioFormat:
        return AudioFormat(
            sample_rate_hz=self.sample_rate_hz, channels=self.samples.shape[1]
        )

    @property
    def frames(self) -> int:
        return self.samples.shape[0]

    @property
    def duration_ms(self) -> float:
        return self.frames / self.sample_rate_hz * 1000


def read_sound(file: Path | BinaryIO) -> Sound:
    """A sound file's sound, whatever its sample rate, channels and sample type."""
    samples, sample_rate_hz = soundfile.read(file, dtype="float32", always_2d=True)
    return Sound(
        samples=np.asarray(samples, dtype=np.float32), sample_rate_hz=sample_rate_hz
    )


def tone_train(units: Sequence[PureToneUnit], *, sample_rate_hz: int) -> Sound:
    """The tones one after another, each at its unit's volume.

    The units carry their samples (``PureToneGenerator.gen_stimulus_unit``), made at
    ``sample_rate_hz``.
    """
    parts: list[NDArray[np.float32]] = []
    for unit in units:
        if unit.stimulus is None:
            raise ValueError("a tone has no samples: generate them before playing")
        gain = 1.0
        for volume in (unit.master_volume, unit.digital_volume):
            if volume is not None:
                gain *= max(0.0, min(1.0, volume / 100))
        parts.append((unit.stimulus / 32768 * gain).astype(np.float32))
    samples = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return Sound(samples=samples.reshape(-1, 1), sample_rate_hz=sample_rate_hz)


def convert(sound: Sound, *, to: AudioFormat) -> Sound:
    """The sound in another format: resampled, and with that format's channels.

    One channel goes to every channel and two channels are averaged into one; any
    other change of channels is refused.
    """
    samples = sound.samples
    if sound.sample_rate_hz != to.sample_rate_hz:
        samples = soxr.resample(
            samples, sound.sample_rate_hz, to.sample_rate_hz, quality="VHQ"
        )
    channels = samples.shape[1]
    if channels == to.channels:
        pass
    elif channels == 1:
        samples = np.repeat(samples, to.channels, axis=1)
    elif to.channels == 1:
        samples = samples.mean(axis=1, keepdims=True)
    else:
        raise ValueError(
            f"a sound of {channels} channels cannot be played on {to.channels}"
        )
    return Sound(
        samples=np.ascontiguousarray(samples, dtype=np.float32),
        sample_rate_hz=to.sample_rate_hz,
    )
