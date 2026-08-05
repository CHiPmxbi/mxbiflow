import unittest

from pygame import Event, Surface

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


class SchedulerTests(unittest.TestCase):
    def test_unknown_animal_uses_configured_animal_stage(self) -> None:
        animal_config = AnimalConfig(name="fallback", stage="targetstage")
        animal = Animal(
            config=animal_config,
            current_stage_name="targetstage",
            stages={"targetstage": StageState(stage_name="targetstage")},
        )
        session = Session(
            config=SessionConfig(
                unknown_animal_as=animal_config.name,
                animals=(animal_config,),
            ),
            state=SessionState(animals={animal.name: animal}),
        )
        scene_manager = SceneManager()
        scene_manager.register([TargetStage])
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


if __name__ == "__main__":
    unittest.main()
