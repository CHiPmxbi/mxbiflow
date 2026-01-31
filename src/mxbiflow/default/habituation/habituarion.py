from pygame.surface import Surface
from pygame.event import Event
from ...models.session import Session
from ...scene_protocol import SceneProtocol


class Habituarion:
    _running: bool

    def __init__(self, session: Session) -> None: ...

    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def handle_event(self, event: Event) -> None: ...

    def update(self, dt_s: float) -> None: ...

    def draw(self, screen: Surface) -> None: ...

    def decide(self) -> type[SceneProtocol]: ...
