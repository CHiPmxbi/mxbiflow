from dataclasses import dataclass
from typing import Callable

from pygame import time


@dataclass
class _Task:
    interval_ms: int
    callback: Callable[[], None]
    repeat: bool
    next_fire_ms: int
    cancelled: bool = False


class FrameTimer:
    def __init__(self) -> None:
        self._tasks: list[_Task] = []

    def after(self, delay_ms: int, callback: Callable[[], None]) -> _Task:
        now = time.get_ticks()
        task = _Task(delay_ms, callback, False, now + delay_ms)
        self._tasks.append(task)
        return task

    def every(self, interval_ms: int, callback: Callable[[], None]) -> _Task:
        now = time.get_ticks()
        task = _Task(interval_ms, callback, True, now + interval_ms)
        self._tasks.append(task)
        return task

    def cancel(self, task: _Task) -> None:
        task.cancelled = True

    def update(self) -> None:
        now = time.get_ticks()
        for task in self._tasks:
            if task.cancelled:
                continue
            if now >= task.next_fire_ms:
                task.callback()
                if task.repeat and not task.cancelled:
                    task.next_fire_ms += task.interval_ms
                else:
                    task.cancelled = True

        self._tasks = [task for task in self._tasks if not task.cancelled]
