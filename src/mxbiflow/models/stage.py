from ..scene.scene_protocol import SceneProtocol
from dataclasses import dataclass


@dataclass
class StageTable:
    _stages: dict[str, type[SceneProtocol]] = {}

    def register(self, stage: type[SceneProtocol], name: str | None = None):
        if name is None:
            name = stage.__name__

        self._stages[stage.__name__] = stage
