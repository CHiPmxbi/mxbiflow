"""A stage of training written in Python: its trial, and what decides around it.

The trial (:class:`~.scene.MachineTrial`) keeps nothing: it is given its values, runs
its machine and gives back a record. The stage is what goes on from trial to trial: it
gives each trial its values (``next_trial``) and reads each record to say whether the
animal moves (``decide``). The scheduler that calls them is the framework's and is not
the stage's to change::

    class Touching(Stage[Params]):
        trial = TouchingTrial

        def next_trial(self) -> Params:
            return Params(reward_ms=choice((300, 500)))

        def decide(self, record: TrialRecord) -> SettlementAction:
            ...

    scene_manager.register([Touching.scene()])

There is one stage object for each animal in a run, so what it keeps in memory lasts
the run; what must outlast it belongs in the session's stage context.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from weakref import WeakKeyDictionary

from inflection import underscore
from pydantic import BaseModel

from ..context import MXBIFlow
from ..models.animal import Animal, StageState
from ..models.session import Session
from ..scene.settlement import SettlementAction
from .host import TrialRecord
from .machine import TrialParams

if TYPE_CHECKING:
    from .scene import MachineTrial


class Stage[P: TrialParams](ABC):
    """A stage for one animal: which trial comes next and when the animal moves."""

    #: The stage's trial.
    trial: ClassVar[type[MachineTrial[Any]]]
    # Shown in cogmote and the experiment manifest, as a scene's are.
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    level_table: ClassVar[dict[str, list[int]]] = {}
    config_model: ClassVar[type[BaseModel] | None] = None
    config_template: ClassVar[Path | None] = None

    _scene: ClassVar[type[MachineTrial[Any]] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._scene = None

    @classmethod
    def name(cls) -> str:
        """The stage's name: the class's in snake case unless overridden."""
        return underscore(cls.__name__)

    @classmethod
    def scene(cls) -> type[MachineTrial[P]]:
        """The scene to register: the stage's trial, bound to this stage."""
        if cls._scene is None:
            cls._scene = type(
                cls.trial.__name__,
                (cls.trial,),
                {
                    "stage_type": cls,
                    "title": cls.title,
                    "description": cls.description,
                    "level_table": cls.level_table,
                    "config_model": cls.config_model,
                    "config_template": cls.config_template,
                },
            )
        return cls._scene

    @classmethod
    def config_document(cls) -> dict[str, Any]:
        """This run's stage configuration document (``Scene.config_document``)."""
        return cls.scene().config_document()

    def __init__(self, *, session: Session, animal: Animal) -> None:
        self.session = session
        self.animal = animal

    @property
    def state(self) -> StageState:
        """The animal's progress in this stage."""
        return self.animal.stages[self.name()]

    @property
    def level(self) -> int:
        """The animal's level in this stage now."""
        return self.state.level

    @abstractmethod
    def next_trial(self) -> P:
        """The values of the animal's next trial."""

    def decide(self, record: TrialRecord) -> SettlementAction:
        """Read a finished trial and say whether the animal moves; by default not.

        Called once for each trial that reached an outcome, before the trial is
        recorded: ``record.action`` is not yet set.
        """
        return SettlementAction.NONE


# The stage objects of each run, by stage class and animal.
_stages: WeakKeyDictionary[MXBIFlow, dict[tuple[type[Stage[Any]], str], Stage[Any]]] = (
    WeakKeyDictionary()
)


def stage_of[S: Stage[Any]](kind: type[S], *, run: MXBIFlow, animal: Animal) -> S:
    """The run's stage object of ``kind`` for ``animal``, made when first asked."""
    stages = _stages.setdefault(run, {})
    key = (kind, animal.name)
    if key not in stages:
        stages[key] = kind(session=run.session, animal=animal)
    stage = stages[key]
    assert isinstance(stage, kind)
    return stage
