from pygame import Event

from mxbiflow.driver.detector.detector import DetectorEvent

from ..models.session import Session
from ..scene import SceneManager
from ..scene.idle.idle import IDLE
from ..utils.logger import logger
from .detector_bridge import EVT_DETECTOR, DetectorMsg


class Scheduler:
    def __init__(
        self,
        session: Session,
        scene_manager: SceneManager,
    ) -> None:
        self._session = session
        self._scene_manager = scene_manager
        self._scenes = self._scene_manager.scenes

        self._need_refresh = False

    def _mark_refresh(self) -> None:
        self._need_refresh = True

    def _set_current_animal(self, animal: str) -> None:
        self._session.set_current_animal(animal)
        self._need_refresh = True

    def _clear_current_animal(self) -> None:
        if self._session.current_animal is None:
            return

        self._session.clear_current_animal()
        self._mark_refresh()

    def level_up(self) -> None:
        """Manually increase the current animal's current stage level."""
        if self._session.current_animal is None:
            return
        self._session.level_up()
        self._mark_refresh()

    def level_down(self) -> None:
        """Manually decrease the current animal's current stage level."""
        animal = self._session.current_animal
        if animal is None or animal.current_stage.level == 0:
            return
        self._session.level_down()
        self._mark_refresh()

    def next_stage(self) -> None:
        """Manually move the current animal to the next configured stage."""
        target = self._session.next_stage
        if target is None:
            return
        if target not in self._scenes:
            logger.debug("manual stage target not registered: %s", target)
            return
        self._session.go_next_stage()
        self._mark_refresh()

    def prev_stage(self) -> None:
        """Manually move the current animal to the previous configured stage."""
        target = self._session.prev_stage
        if target is None:
            return
        if target not in self._scenes:
            logger.debug("manual stage target not registered: %s", target)
            return
        self._session.go_prev_stage()
        self._mark_refresh()

    def _handle_fault_event(self) -> None:
        fallback = self._scene_manager.fault_fallback
        if isinstance(self._scene_manager.current, fallback):
            return

        self._scene_manager.switch(fallback)

    def _handle_unknown_animal(self) -> None:
        self._set_current_animal(self._session.unknown_animal_as)

    def handle_event(self, event: Event) -> None:
        if event.type != EVT_DETECTOR:
            return

        msg: DetectorMsg = event.msg
        logger.debug(
            "detector event received: kind=%s, animal=%s", msg.kind, msg.animal
        )

        match msg.kind:
            case DetectorEvent.FAULT_DETECTED:
                self._handle_fault_event()

            case DetectorEvent.ANIMAL_ENTERED:
                if msg.animal is None:
                    return
                self._set_current_animal(msg.animal)

            case DetectorEvent.UNKNOWN_ANIMAL_ENTERED:
                self._handle_unknown_animal()

            case DetectorEvent.ANIMAL_LEFT:
                self._clear_current_animal()

    def _shoud_refresh(self) -> bool:
        current = self._scene_manager.current
        return (
            current is not None
            and not isinstance(current, IDLE)
            and not current.running
        )

    def update(self) -> None:
        if self._shoud_refresh():
            self._mark_refresh()

        if not self._need_refresh:
            return

        self._need_refresh = False
        self._refresh_by_state()

    def _refresh_by_state(self) -> None:
        animal = self._session.current_animal

        if animal is None:
            if not isinstance(self._scene_manager.current, IDLE):
                self._scene_manager.switch(self._scenes[IDLE.name()])
            return

        stage = animal.current_stage.stage_name
        self._scene_manager.switch(self._scenes[stage])
