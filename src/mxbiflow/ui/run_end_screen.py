"""The rig screen after a run: the summary and the steps, with no confirm step.

It replaces the game loop's window while the steps run on a worker thread and
stays a little longer once they are done, so the outcome can be read on the
rig or over VNC. Input is ignored; nothing waits for an operator.
"""

import time
from collections.abc import Callable, Sequence
from threading import Thread

import pygame
from pymotego import Step

from ..infra.run_end import RunEnd, RunSummary
from ..utils.logger import logger

_FPS = 5
_WHITE = (235, 235, 235)
_GREY = (150, 150, 150)
_GREEN = (90, 200, 120)
_RED = (235, 90, 80)
_YELLOW = (235, 200, 90)


def show_run_end(
    summary: RunSummary,
    steps: RunEnd,
    work: Callable[[], None],
    *,
    size: tuple[int, int],
    fullscreen: bool,
    hold_s: float = 15.0,
) -> None:
    """Run ``work`` on a thread while showing ``summary`` and ``steps``; return once it is done.

    Without a display, ``work`` runs and nothing is shown.
    """
    worker = Thread(target=work, name="run-end")
    try:
        pygame.display.init()
        pygame.font.init()
        screen = pygame.display.set_mode(size, pygame.FULLSCREEN if fullscreen else 0)
    except pygame.error as error:
        logger.warning("run end screen unavailable: %s", error)
        worker.start()
        worker.join()
        return
    worker.start()
    clock = pygame.time.Clock()
    finished_at: float | None = None
    try:
        while finished_at is None or time.monotonic() - finished_at < hold_s:
            pygame.event.get()
            if finished_at is None and not worker.is_alive():
                finished_at = time.monotonic()
            draw(screen, summary, steps.steps, finished=finished_at is not None)
            pygame.display.flip()
            clock.tick(_FPS)
    finally:
        worker.join()
        pygame.display.quit()


def draw(
    screen: pygame.Surface,
    summary: RunSummary,
    steps: Sequence[Step],
    *,
    finished: bool,
) -> None:
    width, height = screen.get_size()
    line = max(height // 26, 14)
    font = pygame.font.Font(None, line)
    title = pygame.font.Font(None, line * 2)
    margin = line
    y = margin

    def text(value: str, x: int, color: tuple[int, int, int] = _WHITE) -> None:
        screen.blit(font.render(value, True, color), (x, y))

    screen.fill((0, 0, 0))
    failed = any(step.state == "failed" for step in steps)
    heading = (
        "Run ended"
        if not finished
        else "Run ended: steps failed"
        if failed
        else "Run ended: all done"
    )
    screen.blit(
        title.render(heading, True, _RED if finished and failed else _WHITE),
        (margin, y),
    )
    y += line * 2
    text(
        f"Session #{summary.session_id}  ·  {_duration(summary.duration_seconds)}",
        margin,
        _GREY,
    )
    y += line * 2

    columns = [
        margin,
        margin + width * 22 // 100,
        margin + width * 34 // 100,
        margin + width * 47 // 100,
        margin + width * 60 // 100,
    ]
    for x, label in zip(
        columns, ["Animal", "Trials", "Accuracy", "Duration", "Stages"], strict=True
    ):
        text(label, x, _GREY)
    y += int(line * 1.2)
    for animal in summary.animals:
        accuracy = "-" if animal.accuracy is None else f"{animal.accuracy:.0%}"
        stages = ", ".join(
            f"{s.name} {s.initial_level}"
            if s.initial_level == s.final_level
            else f"{s.name} {s.initial_level}->{s.final_level}"
            for s in animal.stages
        )
        values = [
            animal.name,
            str(animal.trials),
            accuracy,
            _duration(animal.duration_seconds),
            stages or "-",
        ]
        for x, value in zip(columns, values, strict=True):
            text(value, x)
        y += int(line * 1.2)
    y += line

    bar_x, bar_width = margin + width * 40 // 100, width * 30 // 100
    for step in steps:
        color = {"done": _GREEN, "failed": _RED, "running": _YELLOW}.get(
            step.state, _GREY
        )
        text(step.label or step.name, margin, color)
        fraction = 1.0 if step.state == "done" else _fraction(step)
        pygame.draw.rect(screen, _GREY, (bar_x, y + line // 4, bar_width, line // 2), 1)
        if fraction:
            pygame.draw.rect(
                screen,
                color,
                (bar_x, y + line // 4, int(bar_width * fraction), line // 2),
            )
        text(_state(step), bar_x + bar_width + margin, color)
        y += int(line * 1.2)
        if step.state == "failed":
            then = "retried on the next start" if step.retry else "not retried"
            text(f"{step.reason or 'failed'}  ({then})", margin * 2, _RED)
            y += int(line * 1.2)


def _fraction(step: Step) -> float:
    if step.done is None or not step.total:
        return 0.0
    return min(step.done / step.total, 1.0)


def _state(step: Step) -> str:
    if step.state != "running" or step.total is None:
        return step.state
    if step.unit == "bytes":
        return f"{(step.done or 0) / 1e6:.0f} / {step.total / 1e6:.0f} MB"
    return f"{step.done or 0:.0f} / {step.total:.0f}"


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m {secs}s"
