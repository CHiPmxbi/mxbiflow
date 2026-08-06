import unittest

from pygame import Event, Surface

from mxbiflow.driver import MXBIModel
from mxbiflow.driver.detector.detector import DetectorEvent
from mxbiflow.gameloop.detector_bridge import EVT_DETECTOR, DetectorMsg
from mxbiflow.gameloop.scheduler import Scheduler
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.scene import SceneManager
from mxbiflow.scene.scene import Scene


class TargetStage(Scene):
    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None:
        pass

    def update(self, dt_s: float) -> None:
        pass

    def draw(self, screen: Surface) -> None:
        pass


class StageA(Scene):
    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None:
        pass

    def update(self, dt_s: float) -> None:
        pass

    def draw(self, screen: Surface) -> None:
        pass


class StageB(StageA):
    pass


class StageC(StageA):
    pass


class SchedulerTests(unittest.TestCase):
    def test_unknown_animal_uses_configured_animal_stage(self) -> None:
        animal_config = AnimalConfig(name="fallback", stage="target_stage")
        animal = Animal(
            config=animal_config,
            current_stage_name="target_stage",
            stages={"target_stage": StageState(stage_name="target_stage")},
        )
        session = Session(
            config=SessionConfig(
                unknown_animal_as=animal_config.name,
                animals=(animal_config,),
            ),
            mxbi_config=MXBIModel(
                backup_source_root_id="source",
                backup_destination_root_id="destination",
            ),
            state=SessionState(animals={animal.name: animal}),
        )
        scene_manager = SceneManager()
        scene_manager.register([TargetStage])
        self.assertIs(scene_manager.scenes["target_stage"], TargetStage)
        scheduler = Scheduler(session, scene_manager)

        scheduler.handle_event(
            Event(
                EVT_DETECTOR,
                msg=DetectorMsg(
                    kind=DetectorEvent.UNKNOWN_ANIMAL_ENTERED,
                    animal="unrecognized-rfid",
                ),
            )
        )
        scheduler.update()
        scene_manager.apply_pending()

        self.assertIs(session.current_animal, animal)
        self.assertIsInstance(scene_manager.current, TargetStage)


class ManualControlTests(unittest.TestCase):
    @staticmethod
    def _make_session(
        *,
        stage: str = "stage_a",
        level: int = 0,
        stage_order: tuple[str, ...] = (),
    ) -> tuple[Session, Animal]:
        animal_config = AnimalConfig(
            name="animal-a",
            stage=stage,
            level=level,
            stage_order=stage_order,
        )
        animal = Animal(
            config=animal_config,
            current_stage_name=stage,
            stages={stage: StageState(stage_name=stage, level=level)},
        )
        session = Session(
            config=SessionConfig(
                unknown_animal_as=animal_config.name,
                animals=(animal_config,),
            ),
            mxbi_config=MXBIModel(
                backup_source_root_id="source",
                backup_destination_root_id="destination",
            ),
            state=SessionState(animals={animal.name: animal}),
        )
        return session, animal

    @staticmethod
    def _make_scheduler(session: Session) -> tuple[Scheduler, SceneManager]:
        scene_manager = SceneManager()
        scene_manager.register([StageA, StageB, StageC])
        return Scheduler(session, scene_manager), scene_manager

    def test_manual_level_up_increases_level_and_refreshes_scene(self) -> None:
        session, animal = self._make_session(level=2)
        scheduler, scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.level_up()

        self.assertEqual(animal.current_stage.level, 3)
        scheduler.update()
        scene_manager.apply_pending()
        self.assertIsInstance(scene_manager.current, StageA)

    def test_manual_level_down_decreases_level(self) -> None:
        session, animal = self._make_session(level=2)
        scheduler, _scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.level_down()

        self.assertEqual(animal.current_stage.level, 1)

    def test_manual_level_down_at_zero_is_noop(self) -> None:
        session, animal = self._make_session(level=0)
        scheduler, _scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.level_down()

        self.assertEqual(animal.current_stage.level, 0)

    def test_manual_controls_are_noop_without_current_animal(self) -> None:
        session, animal = self._make_session(level=2)
        scheduler, _scene_manager = self._make_scheduler(session)

        scheduler.level_up()
        scheduler.level_down()
        scheduler.next_stage()
        scheduler.prev_stage()

        self.assertEqual(animal.current_stage.level, 2)
        self.assertEqual(animal.current_stage_name, "stage_a")

    def test_manual_next_stage_moves_to_next_configured_stage(self) -> None:
        session, _animal = self._make_session(
            stage="stage_a",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        scheduler, scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.next_stage()

        self.assertEqual(session.current_animal.current_stage_name, "stage_b")
        scheduler.update()
        scene_manager.apply_pending()
        self.assertIsInstance(scene_manager.current, StageB)

    def test_manual_prev_stage_moves_to_previous_configured_stage(self) -> None:
        session, _animal = self._make_session(
            stage="stage_b",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        scheduler, _scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.prev_stage()

        self.assertEqual(session.current_animal.current_stage_name, "stage_a")

    def test_manual_stage_navigation_noop_when_target_not_registered(self) -> None:
        session, _animal = self._make_session(
            stage="stage_a",
            stage_order=("stage_a", "stage_unregistered"),
        )
        scheduler, _scene_manager = self._make_scheduler(session)
        session.set_current_animal("animal-a")

        scheduler.next_stage()

        self.assertEqual(session.current_animal.current_stage_name, "stage_a")


if __name__ == "__main__":
    unittest.main()
