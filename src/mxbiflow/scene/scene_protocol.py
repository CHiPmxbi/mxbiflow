from typing import Protocol, runtime_checkable

from pygame.event import Event
from pygame.surface import Surface


@runtime_checkable
class SceneProtocol(Protocol):
    _running: bool

    def start(self) -> None: ...

    def quit(self) -> None: ...

    @property
    def running(self) -> bool: ...

    def handle_event(self, event: Event) -> None: ...

    def update(self, dt_s: float) -> None: ...

    def draw(self, screen: Surface) -> None: ...
