import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch
from urllib.parse import quote

from pygame import MOUSEBUTTONDOWN, Event, Surface

from mxbiflow.driver import MXBIModel
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.scene import LevelCounts, Wiring, machine_scenes


def state(name: str, **parts: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "group": None,
        "hold": [],
        "timeout": None,
        "onEntry": [],
        "transitions": [],
    }
    return base | parts


def stage(
    name: str,
    screen: tuple[int, int] = (200, 100),
    target: tuple[int, int] = (150, 20),
) -> dict[str, Any]:
    """Touch the target for a reward; leaving the beam ends the trial."""
    level = {"values": {}, "types": [], "order": "random"}
    return {
        "name": name,
        "machine": {
            "channels": {"inputs": ["beam"], "outputs": ["reward"]},
            "parameters": [{"name": "reward_ms", "type": "time", "default": 50}],
            "timers": [],
            "generators": [],
            "counters": [],
            "start": "choice",
            "groups": [],
            "states": [
                state(
                    "choice",
                    onEntry=[{"show": "target"}, {"play": "cue"}],
                    transitions=[
                        {"event": "target.touch", "target": "reward"},
                        {"event": "screen.touch", "target": "error"},
                        {"event": "beam.fall", "target": "exit"},
                    ],
                ),
                state(
                    "reward",
                    hold=["reward"],
                    timeout={"param": "reward_ms"},
                    onEntry=[{"clear": True}],
                    transitions=[{"event": "timeout", "target": "exit"}],
                ),
                state(
                    "error",
                    timeout=10,
                    transitions=[{"event": "timeout", "target": "exit"}],
                ),
            ],
            "layout": {},
            "screen": {"width": screen[0], "height": screen[1]},
            "stimuli": [
                {
                    "kind": "rect",
                    "name": "target",
                    "x": target[0],
                    "y": target[1],
                    "width": 20,
                    "height": 20,
                    "color": "#ff0000",
                },
                {
                    "kind": "tones",
                    "name": "cue",
                    "tones": [
                        {"frequency": 1000, "duration": 100},
                        {"frequency": 0, "duration": 100},
                    ],
                    "duration": 250,
                },
            ],
        },
        "outcomes": {"reward": "correct", "error": "incorrect"},
        "levels": [{"name": "easy", **level}, {"name": "hard", **level}],
        "progression": {"rule": "count", "correct": 2},
    }


WIRING = Wiring(inputs={"beam": 0}, outputs={"reward": 0})


def experiment(*stages: dict[str, Any]) -> Experiment:
    return Experiment.model_validate({"stages": list(stages), "animals": []})


class MachineSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.now = 0
        ticks = patch("pygame.time.get_ticks", side_effect=lambda: self.now)
        ticks.start()
        self.addCleanup(ticks.stop)

        self.detector = SimpleNamespace(current_animal="a")
        self.rewarder = Mock()
        self.aplayer = Mock(frequency_response_table=None)

    def context(
        self,
        scenes: Experiment,
        *,
        rig: tuple[int, int] = (200, 100),
    ) -> SimpleNamespace:
        config = AnimalConfig(name="a", stage=scenes.stages[0].name)
        animal = Animal(
            config=config,
            current_stage_name=config.stage,
            stages={config.stage: StageState(stage_name=config.stage)},
        )
        self.session = Session(
            config=SessionConfig(unknown_animal_as="a", animals=(config,)),
            mxbi_config=MXBIModel(),
            state=SessionState(animals={"a": animal}),
        )
        self.session.start(self.data)
        self.session.set_current_animal("a")
        self.publish = Mock()
        mxbi = SimpleNamespace(
            screen_size=SimpleNamespace(width=rig[0], height=rig[1]),
            aplayer=self.aplayer,
            get_detector=lambda _id: self.detector,
            get_rewarder=lambda _id: self.rewarder,
        )
        return SimpleNamespace(
            session=self.session, mxbi=mxbi, publish_trial=self.publish
        )

    def trial(self, scenes: Experiment, context: SimpleNamespace):
        """Start the next trial of the animal's stage at the current time."""
        animal = self.session.require_current_animal()
        with patch("mxbiflow.statemachine.scene.get_mxbiflow", return_value=context):
            scene = machine_scenes(scenes, WIRING)[animal.current_stage_name]()
        scene.start()
        return scene

    def touch(self, scene, pos: tuple[int, int], at: int) -> None:
        self.now = at
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=pos))
        scene.update(0)

    def records(self, stage_name: str) -> list[dict[str, Any]]:
        path = self.session.absolute_animal_data_path("a") / stage_name / "result.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_a_touched_trial_drives_the_rig_and_is_recorded(self) -> None:
        scenes = experiment(stage("touch"))
        scene = self.trial(scenes, self.context(scenes))
        self.aplayer.play_puretone_sequence.assert_called_once()
        units = self.aplayer.play_puretone_sequence.call_args.args[0]
        # The train is cut at the sound's 250 ms.
        self.assertEqual(
            [(u.frequency_hz, u.duration_ms) for u in units],
            [(1000, 100), (0, 100), (1000, 50)],
        )
        screen = Surface((200, 100))
        scene.draw(screen)
        self.assertEqual(screen.get_at((150, 20)), (255, 0, 0, 255))

        self.touch(scene, (155, 25), at=100)
        self.rewarder.give_reward.assert_called_once()
        # The cue is cut short when the trial moves on and clears the screen.
        scene.draw(screen)
        self.assertEqual(screen.get_at((150, 20)), (0, 0, 0, 255))
        self.assertTrue(scene.running)

        self.now = 160
        scene.update(0)
        self.rewarder.stop_reward.assert_called_once()
        self.assertFalse(scene.running)

        (record,) = self.records("touch")
        self.assertEqual(
            {key: record[key] for key in ("animal", "trial", "stage", "level")},
            {"animal": "a", "trial": 1, "stage": "touch", "level": "easy"},
        )
        self.assertEqual(record["outcome"], "correct")
        self.assertEqual(record["values"], {"reward_ms": 50})
        self.assertEqual(
            record["states"],
            [{"state": "choice", "t": 0}, {"state": "reward", "t": 100}],
        )
        self.assertEqual(record["events"][-1], {"t": 150, "text": "trial ends"})
        self.publish.assert_called_once()
        self.assertIs(self.publish.call_args.kwargs["correct"], True)

    def test_correct_trials_move_the_animal_through_levels_and_stages(self) -> None:
        scenes = experiment(stage("first"), stage("second"))
        context = self.context(scenes)
        actions: list[str] = []
        for _ in range(4):
            start = self.now
            scene = self.trial(scenes, context)
            self.touch(scene, (150, 20), at=start + 10)
            self.now = start + 100
            scene.update(0)
            actions.append(self.records("first")[-1]["action"])

        self.assertEqual(actions, ["none", "level up", "none", "next stage"])
        animal = self.session.require_current_animal()
        self.assertEqual(animal.current_stage_name, "second")
        self.assertEqual(animal.current_stage.level, 0)
        self.assertEqual(animal.stages["first"].level, 1)
        self.assertEqual(
            animal.current_stage.get_context("machine", LevelCounts),
            LevelCounts(level=0),
        )

    def test_a_trial_the_animal_leaves_is_recorded_but_not_counted(self) -> None:
        scenes = experiment(stage("touch"))
        scene = self.trial(scenes, self.context(scenes))

        self.now = 40
        scene.quit()

        self.assertFalse(scene.running)
        (record,) = self.records("touch")
        self.assertEqual(record["outcome"], "none")
        self.assertEqual(record["events"][-1], {"t": 40, "text": "trial stopped"})
        counts = self.session.require_current_animal().current_stage.get_context(
            "machine", LevelCounts
        )
        self.assertEqual(counts, LevelCounts(level=0))

    def test_an_input_follows_its_detector(self) -> None:
        scenes = experiment(stage("touch"))
        scene = self.trial(scenes, self.context(scenes))

        self.detector.current_animal = None
        self.now = 30
        scene.update(0)

        self.assertFalse(scene.running)
        self.assertEqual(
            self.records("touch")[0]["events"][-2:],
            [{"t": 30, "text": "beam.fall → exit"}, {"t": 30, "text": "trial ends"}],
        )

    def test_an_upright_screen_is_drawn_and_touched_turned(self) -> None:
        # The animal sees 100×200, its top at the right edge of the rig's 200×100.
        scenes = experiment(stage("touch", screen=(100, 200), target=(20, 150)))
        scene = self.trial(scenes, self.context(scenes))
        screen = Surface((200, 100))
        scene.draw(screen)
        self.assertEqual(screen.get_at((50, 20)), (255, 0, 0, 255))

        self.touch(scene, (50, 20), at=10)

        self.rewarder.give_reward.assert_called_once()

    def test_a_picture_is_read_from_a_percent_encoded_svg_data_url(self) -> None:
        raw = stage("touch")
        raw["machine"]["stimuli"][0] = {
            "kind": "image",
            "name": "target",
            "x": 150,
            "y": 20,
            "width": 20,
            "height": 20,
            "image": "data:image/svg+xml;charset=utf-8,"
            + quote(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                '<rect width="10" height="10" fill="#00ff00"/></svg>'
            ),
        }
        scenes = experiment(raw)
        scene = self.trial(scenes, self.context(scenes))
        screen = Surface((200, 100))

        scene.draw(screen)

        self.assertEqual(screen.get_at((150, 20)), (0, 255, 0, 255))

    def test_an_unmapped_channel_fails_with_its_name(self) -> None:
        with self.assertRaisesRegex(ValueError, 'output "reward"'):
            machine_scenes(experiment(stage("touch")), Wiring(inputs={"beam": 0}))

    def test_a_screen_of_another_size_fails(self) -> None:
        scenes = experiment(stage("touch", screen=(300, 300)))

        with self.assertRaisesRegex(ValueError, "300×300"):
            self.trial(scenes, self.context(scenes))
