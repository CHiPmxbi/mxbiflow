from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


class Next(Protocol):
    def __call__(self) -> None: ...


class Step(Protocol):
    def __call__(self, next_t: Next) -> None: ...


@dataclass
class Flow[T]:
    ctx: T
    _steps: list[Step] = field(default_factory=list)
    _i: int = 0
    _stopped: bool = False

    @classmethod
    def start(cls, ctx: T) -> Flow[T]:
        return cls(ctx=ctx, _steps=[])

    def do(self, fn: Callable[[T], None]) -> Flow[T]:
        def _step(next_t: Next) -> None:
            fn(self.ctx)
            next_t()

        self._steps.append(_step)
        return self

    def then(self, step: Step) -> Flow:
        self._steps.append(step)
        return self

    def run(self) -> None:
        self._next()

    def stop(self) -> None:
        self._stopped = True

    def _next(self) -> None:
        if self._stopped or self._i >= len(self._steps):
            return

        step = self._steps[self._i]
        self._i += 1

        called = False

        def once() -> None:
            nonlocal called
            if called or self._stopped:
                return

            called = True
            self._next()

        step(once)
