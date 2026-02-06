from pathlib import Path

from pydantic import RootModel
from pygame import Event, Surface

from .scene_protocol import SceneProtocol


class Scenes(RootModel):
    root: list[str]


class SceneManager:
    scenes: dict[str, type[SceneProtocol]] = {}

    def __init__(self) -> None:
        self.current: SceneProtocol | None = None
        self._pending: SceneProtocol | None = None

    def persist(self, path: Path) -> None:
        scenes = Scenes(root=list(self.scenes.keys()))
        json_data = scenes.model_dump_json()

        with path.open("w") as f:
            f.write(json_data)

    def register(self, scene: type[SceneProtocol], name: str | None = None) -> None:
        if name is None:
            name = scene.__name__.lower()

        self.scenes[name] = scene

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
