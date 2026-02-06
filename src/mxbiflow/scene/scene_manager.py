from pathlib import Path

from pygame import Event, Surface

from ..config_store import ConfigStore
from ..models.session import Options
from .scene_protocol import SceneProtocol


class SceneManager:
    _scenes: dict[str, type[SceneProtocol]] = {}

    def __init__(self) -> None:
        self.current: SceneProtocol | None = None
        self._pending: SceneProtocol | None = None

    def persist(self, path: Path) -> None:
        options_store = ConfigStore(path, Options)

        options_store.value.stages = list(self._scenes.keys())
        options_store.save()

    def register(
        self, scene: dict[str, type[SceneProtocol]] | list[type[SceneProtocol]]
    ) -> None:
        if isinstance(scene, dict):
            self._scenes.update(scene)
        elif isinstance(scene, list):
            for s in scene:
                self._scenes[s.__name__.lower()] = s
        else:
            raise ValueError("Invalid scene type")

    @property
    def scenes(self) -> dict[str, type[SceneProtocol]]:
        return self._scenes

    def switch(self, scene: type[SceneProtocol], defer: bool = True) -> None:
        if defer:
            self._pending = scene()
        else:
            self._switch(scene())

    def _switch(self, next_scene: SceneProtocol) -> None:
        prev = self.current
        if prev is not None and prev.running:
            prev.quit()

        self.current = next_scene
        next_scene.start()

    def apply_pending(self) -> None:
        if self._pending is None:
            return
        next_scene = self._pending
        self._pending = None
        self._switch(next_scene)

    def handle_event(self, event: Event) -> None:
        if self.current:
            self.current.handle_event(event)

    def update(self, dt_s: float) -> None:
        if self.current:
            self.current.update(dt_s)

    def draw(self, screen: Surface) -> None:
        if self.current:
            self.current.draw(screen)
