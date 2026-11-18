"""Delays on the game loop's clock."""

from collections.abc import Callable
from dataclasses import dataclass

from pygame import time

from ..task import Task, TaskResult, TaskStatus


@dataclass
class _Timed:
    task: Task
    callback: Callable[[], None]
    next_fire_ms: int
    #: The time between calls of a repeating delay; ``None`` fires once.
    interval_ms: int | None


class FrameTimer:
    """Calls back after a delay, when the game loop updates it.

    A delay is a :class:`~mxbiflow.task.Task`: it finishes when it has fired (a
    repeating one never does) and can be cancelled.
    """

    def __init__(self) -> None:
        self._timed: list[_Timed] = []

    def after(self, delay_ms: int, callback: Callable[[], None]) -> Task:
        return self._add(delay_ms=delay_ms, callback=callback, repeat=False)

    def every(self, interval_ms: int, callback: Callable[[], None]) -> Task:
        return self._add(delay_ms=interval_ms, callback=callback, repeat=True)

    def _add(
        self, *, delay_ms: int, callback: Callable[[], None], repeat: bool
    ) -> Task:
        task = Task()
        self._timed.append(
            _Timed(
                task=task,
                callback=callback,
                next_fire_ms=time.get_ticks() + delay_ms,
                interval_ms=delay_ms if repeat else None,
            )
        )
        return task

    def cancel(self, task: Task) -> None:
        task.cancel()

    def cancel_all(self) -> None:
        timed, self._timed = self._timed, []
        for item in timed:
            item.task.complete(TaskResult(TaskStatus.CANCELLED))

    def update(self) -> None:
        now = time.get_ticks()
        for item in list(self._timed):
            task = item.task
            if task.cancel_requested:
                task.complete(TaskResult(TaskStatus.CANCELLED))
            elif now >= item.next_fire_ms:
                item.callback()
                if item.interval_ms is None:
                    task.complete(TaskResult(TaskStatus.FINISHED))
                elif task.cancel_requested:
                    task.complete(TaskResult(TaskStatus.CANCELLED))
                else:
                    item.next_fire_ms += item.interval_ms
        self._timed = [item for item in self._timed if not item.task.done]
