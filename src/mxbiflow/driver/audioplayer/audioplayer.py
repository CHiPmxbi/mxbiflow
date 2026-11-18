"""Plays sounds on the rig's audio output."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice
from numpy.typing import NDArray

from mxbiflow.task import Task

from .frequency_response_table import FrequencyResponseTable
from .mixer import Mixer
from .sound import AudioFormat, Sound, convert, read_sound

logger = logging.getLogger(__name__)


class AudioPlayer:
    """One output stream, kept open, on which any number of sounds play together.

    The stream has one format. A sound is converted to it once, when it is loaded
    (``load``) or prepared (``prepare``), so a file of any sample rate plays and
    nothing is converted while a trial runs. ``play`` gives a
    :class:`~mxbiflow.task.Task` that ends with the sound; the game loop's ``update``
    runs its callbacks.

    ``sample_rate_hz`` of ``None`` is the output device's own default. The stream
    opens with ``open`` or with the first sound.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int | None = None,
        channels: int = 2,
        blocksize: int = 256,
        frequency_response_table: FrequencyResponseTable | None = None,
    ) -> None:
        if blocksize <= 0:
            raise ValueError("blocksize must be positive")
        self._sample_rate_hz = sample_rate_hz
        self._channels = channels
        self._blocksize = blocksize
        self._frequency_response_table = frequency_response_table
        self._mixer: Mixer | None = None
        self._stream: sounddevice.OutputStream | None = None

    @property
    def frequency_response_table(self) -> FrequencyResponseTable | None:
        return self._frequency_response_table

    @property
    def format(self) -> AudioFormat:
        """The format every sound is played in."""
        return self._open().format

    def open(self) -> None:
        """Open the output; a format the device does not take fails here."""
        self._open()

    def _open(self) -> Mixer:
        if self._mixer is not None:
            return self._mixer
        sample_rate_hz = self._sample_rate_hz
        if sample_rate_hz is None:
            device: Any = sounddevice.query_devices(kind="output")
            sample_rate_hz = round(device["default_samplerate"])
        mixer = Mixer(
            format=AudioFormat(sample_rate_hz=sample_rate_hz, channels=self._channels)
        )

        def callback(
            out: NDArray[np.float32], _frames: int, _time: Any, status: Any
        ) -> None:
            if status:
                logger.warning("audio output: %s", status)
            mixer.render(out)

        self._stream = sounddevice.OutputStream(
            samplerate=sample_rate_hz,
            channels=self._channels,
            dtype="float32",
            blocksize=self._blocksize,
            latency="low",
            callback=callback,
        )
        self._stream.start()
        self._mixer = mixer
        logger.info(
            "audio output open: %d Hz, %d channels", sample_rate_hz, self._channels
        )
        return mixer

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
        if self._mixer is not None:
            self._mixer.close()
        self._stream = None
        self._mixer = None

    def load(self, path: Path) -> Sound:
        """A sound file's sound, ready to play."""
        return self.prepare(read_sound(path))

    def prepare(self, sound: Sound) -> Sound:
        """The sound in the output's format, ready to play."""
        return convert(sound, to=self.format)

    def play(self, sound: Sound, *, gain: float = 1.0) -> Task:
        """Start a prepared sound with the output's next block."""
        return self._open().add(sound=sound, gain=gain)

    def cancel_all(self) -> None:
        if self._mixer is not None:
            self._mixer.cancel_all()

    def update(self) -> None:
        if self._mixer is not None:
            self._mixer.update()
