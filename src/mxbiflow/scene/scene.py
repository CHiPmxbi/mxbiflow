from abc import ABC, abstractmethod
from typing import ClassVar

from pygame.event import Event
from pygame.surface import Surface


class Scene(ABC):
    level_table: ClassVar[dict[str, list[int]]] = {}

    def __init__(self) -> None:
        self._running: bool = False

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def quit(self) -> None: ...

    @property
    def running(self) -> bool:
        return self._running

    @abstractmethod
    def handle_event(self, event: Event) -> None: ...

    @abstractmethod
    def update(self, dt_s: float) -> None: ...

    @abstractmethod
    def draw(self, screen: Surface) -> None: ...
