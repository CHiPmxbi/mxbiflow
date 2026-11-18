"""Mixes the sounds that are playing into the output's blocks."""

import logging
from dataclasses import dataclass
from queue import Empty, SimpleQueue
from threading import Lock

import numpy as np
from numpy.typing import NDArray

from mxbiflow.task import Task, TaskResult, TaskStatus

from .sound import AudioFormat, Sound

logger = logging.getLogger(__name__)


@dataclass
class _Voice:
    task: Task
    sound: Sound
    gain: float
    #: The next frame to play.
    cursor: int = 0


class Mixer:
    """The sounds playing on one output, summed block by block.

    ``render`` runs on the audio thread; everything else on the game loop's, where
    ``update`` ends the tasks of the sounds that have finished.
    """

    def __init__(self, *, format: AudioFormat) -> None:
        self.format = format
        self._lock = Lock()
        self._voices: list[_Voice] = []
        self._ended: SimpleQueue[tuple[Task, TaskStatus]] = SimpleQueue()
        self._clipped_blocks = 0

    def add(self, *, sound: Sound, gain: float) -> Task:
        """Start ``sound`` with the next block; it must be in the mixer's format."""
        if sound.format != self.format:
            raise ValueError(
                f"the sound is {sound.format}, the output {self.format}: "
                "convert it before playing"
            )
        task = Task()
        with self._lock:
            self._voices.append(_Voice(task=task, sound=sound, gain=gain))
        return task

    def cancel_all(self) -> None:
        with self._lock:
            for voice in self._voices:
                voice.task.cancel()

    def close(self) -> None:
        """End every sound now; for when the output is closed and renders no more."""
        with self._lock:
            voices, self._voices = self._voices, []
        for voice in voices:
            voice.task.complete(TaskResult(TaskStatus.CANCELLED))
        self.update()

    def render(self, out: NDArray[np.float32]) -> None:
        """Fill ``out`` (frames by channels) with the next block of every sound."""
        out.fill(0)
        frames = out.shape[0]
        with self._lock:
            playing: list[_Voice] = []
            for voice in self._voices:
                if voice.task.cancel_requested:
                    self._ended.put((voice.task, TaskStatus.CANCELLED))
                    continue
                block = voice.sound.samples[voice.cursor : voice.cursor + frames]
                out[: block.shape[0]] += block * voice.gain
                voice.cursor += frames
                if voice.cursor >= voice.sound.frames:
                    self._ended.put((voice.task, TaskStatus.FINISHED))
                else:
                    playing.append(voice)
            self._voices = playing
        if np.abs(out).max(initial=0) > 1:
            self._clipped_blocks += 1
            np.clip(out, -1, 1, out=out)

    def update(self) -> None:
        """End the tasks of finished sounds, and say when the sum was too loud."""
        while True:
            try:
                task, status = self._ended.get_nowait()
            except Empty:
                break
            task.complete(TaskResult(status))
        if self._clipped_blocks:
            clipped, self._clipped_blocks = self._clipped_blocks, 0
            logger.warning(
                "the sounds playing together were too loud: %d blocks clipped", clipped
            )
