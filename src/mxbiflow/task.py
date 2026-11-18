"""Something that was started and ends by itself or is cancelled: a time, a sound.

The timer and the audio player hand out the same :class:`Task`, so a stage waits for a
delay and for the end of a sound in one way: ``task.on_done(callback)``, ``task.cancel()``.
Callbacks run on the game loop's thread, when the owner of the task is updated.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from threading import Event


class TaskStatus(Enum):
    FINISHED = auto()
    CANCELLED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class TaskResult:
    status: TaskStatus
    error: Exception | None = None


type DoneCallback = Callable[[TaskResult], None]


class Task:
    def __init__(self) -> None:
        # Read by the thread that does the work; everything else is the game loop's.
        self._cancel = Event()
        self._result: TaskResult | None = None
        self._callbacks: list[DoneCallback] = []

    def cancel(self) -> None:
        """Ask for the task to end; it is done once its owner has been updated."""
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def result(self) -> TaskResult | None:
        """How the task ended, or ``None`` while it runs."""
        return self._result

    @property
    def done(self) -> bool:
        return self._result is not None

    def on_done(self, callback: DoneCallback) -> None:
        """Call ``callback`` with the result when the task ends; at once if it has."""
        if self._result is not None:
            callback(self._result)
        else:
            self._callbacks.append(callback)

    def complete(self, result: TaskResult) -> None:
        """End the task; for its owner, on the game loop's thread."""
        if self._result is not None:
            return
        self._result = result
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(result)
