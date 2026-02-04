from .scene import SceneManager
from .detector_bridge import EVT_DETECTOR, DetectorMsg
from pygame import Event
from pymxbi.detector.detector import DetectorEvent
from .models.session import Session
from .default import IDLE


class Scheduler:
    def __init__(
        self,
        session: Session,
        scene_manager: SceneManager,
    ) -> None:
        self._scene_manager = scene_manager
        self._scenes = self._scene_manager.scenes
        self._session = session

        self._need_refresh = False

    def _set_active_animal(self, animal: str) -> None:

        self._session.set_active_animal(animal)
        self._need_refresh = True

    def _add_animal_session(self) -> None:
        if self._session.active_animal is None:
            return

        self._session.active_animal.add_animal_session()

    def _remove_active_animal(self) -> None:
        if self._session.active_animal is None:
            return

        self._session.remove_active_animal()
        self._need_refresh = True

    def _set_next_stage(self, stage: str) -> None:
        if self._session.active_animal is None:
            return

        self._session.active_animal.set_stage(stage)
        self._need_refresh = True

    def _set_error_stage(self) -> None:
        self._set_next_stage("error")

    def handle_event(self, event: Event) -> None:
        if event.type != EVT_DETECTOR:
            return

        msg: DetectorMsg = event.msg

        match msg.kind:
            case DetectorEvent.FAULT_DETECTED:
                self._set_error_stage()

            case DetectorEvent.ANIMAL_ENTERED:
                if msg.animal is None:
                    return
                self._set_active_animal(msg.animal)
                self._add_animal_session()

            case _:
                ...

    def update(self) -> None:
        current = self._scene_manager.current

        if (
            current is not None
            and not isinstance(current, IDLE)
            and not current.running
        ):
            next_stage = current.decide()
            if next_stage is not None:
                self._set_next_stage(next_stage.__name__.lower())

        if not self._need_refresh:
            return

        self._need_refresh = False
        self._refresh_by_state()

    def _refresh_by_state(self) -> None:
        animal = self._session.active_animal

        if animal is None:
            if not isinstance(self._scene_manager.current, IDLE):
                self._scene_manager.switch(self._scenes[IDLE.__name__.lower()])
            return

        if animal.stage is None:
            animal.set_stage(IDLE.__name__.lower())
            self._scene_manager.switch(self._scenes[IDLE.__name__.lower()])
            return

        stage = animal.stage.name
        self._scene_manager.switch(self._scenes[stage])
