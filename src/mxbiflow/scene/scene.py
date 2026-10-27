import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from inflection import underscore
from pydantic import BaseModel
from pygame.event import Event
from pygame.surface import Surface


class Scene(ABC):
    level_table: ClassVar[dict[str, list[int]]] = {}
    # Shown in cogmote and the experiment manifest (CHiPmxbi/mxbiflow#201).
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    # The stage configuration model and its config.json, the default template.
    config_model: ClassVar[type[BaseModel] | None] = None
    config_template: ClassVar[Path | None] = None

    @classmethod
    def config_document(cls) -> dict[str, Any]:
        """Return this run's stage configuration document.

        It is the one cogmote sent for this stage with the run's configuration,
        else the stage's ``config.json`` template. Pass it to
        :func:`~mxbiflow.models.stage_config.for_animal`.
        """
        from ..core.context import get_mxbiflow

        document = get_mxbiflow().session.config.stage_configs.get(cls.name())
        if document is not None:
            return dict(document)
        if cls.config_template is None:
            raise ValueError(f"stage {cls.name()} has no config template")
        return json.loads(cls.config_template.read_text(encoding="utf-8"))

    @classmethod
    def name(cls) -> str:
        """Return the canonical snake-case scene name."""
        return underscore(cls.__name__)

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
