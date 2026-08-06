from pygame import Event, Surface

from .idle.idle import IDLE
from .scene import Scene


class SceneManager:
    _scenes: dict[str, type[Scene]]

    def __init__(self) -> None:
        self._scenes = {}

        self.current: Scene | None = None
        self._pending: Scene | None = None
        self._default_scene: type[Scene] = IDLE
        self._fault_fallback: type[Scene] = IDLE

        self.register([IDLE])

    def init(self) -> None:
        self.switch(self._default_scene, defer=False)

    def register(self, scene: dict[str, type[Scene]] | list[type[Scene]]) -> None:
        if isinstance(scene, dict):
            self._scenes.update(scene)
        else:
            for s in scene:
                self._scenes[s.name()] = s

    @property
    def scenes(self) -> dict[str, type[Scene]]:
        return self._scenes

    @property
    def stage_level_tables(self) -> dict[str, dict[str, list[int]]]:
        return {name: scene.level_table for name, scene in self._scenes.items()}

    @property
    def default_scene(self) -> type[Scene]:
        return self._default_scene

    @default_scene.setter
    def default_scene(self, name: str) -> None:
        self._default_scene = self._scenes[name]

    @property
    def fault_fallback(self) -> type[Scene]:
        return self._fault_fallback

    @fault_fallback.setter
    def fault_fallback(self, name: str) -> None:
        self._fault_fallback = self._scenes[name]

    def switch(self, scene: type[Scene], defer: bool = True) -> None:
        if defer:
            self._pending = scene()
        else:
            self._switch(scene())

    def _switch(self, next_scene: Scene) -> None:
        prev = self.current
        if prev is not None and prev.running:
            prev.quit()

        self.current = next_scene
        next_scene.start()

    def apply_pending(self) -> bool:
        if self._pending is None:
            return False
        next_scene = self._pending
        self._pending = None
        self._switch(next_scene)
        return True

    def handle_event(self, event: Event) -> None:
        if self.current:
            self.current.handle_event(event)

    def update(self, dt_s: float) -> None:
        if self.current:
            self.current.update(dt_s)

    def draw(self, screen: Surface) -> None:
        if self.current:
            self.current.draw(screen)
