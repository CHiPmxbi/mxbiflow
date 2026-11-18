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
from mxbiflow.driver.audioplayer import AudioFormat
from mxbiflow.driver.channels import DetectorInput, RewarderOutput
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.scene import machine_scenes


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
    target: tuple[float, float] = (0.75, 0.2),
    size: float = 20,
) -> dict[str, Any]:
    """Touch the target for a reward; leaving the beam ends the trial."""
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
                    "size": "px",
                    "width": size,
                    "height": size,
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
    }


def experiment(*stages: dict[str, Any]) -> Experiment:
    return Experiment.model_validate({"stages": list(stages)})


class MachineSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.now = 0
        # Milliseconds, for the scene's clock and the channels'.
        for clock in ("mxbiflow.statemachine.scene", "mxbiflow.driver.channels"):
            patcher = patch(f"{clock}.monotonic", side_effect=lambda: self.now / 1000)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.detector: Any = SimpleNamespace(current_animal="a")
        self.rewarder = Mock()
        # An output of 8000 Hz and one channel: eight frames are a millisecond.
        self.aplayer = Mock(
            frequency_response_table=None,
            format=AudioFormat(sample_rate_hz=8000, channels=1),
            prepare=lambda sound: sound,
        )

    def context(
        self,
        scenes: Experiment,
        *,
        rig: tuple[int, int] = (200, 100),
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
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
            inputs={"beam": DetectorInput(self.detector)} if inputs is None else inputs,
            outputs={"reward": RewarderOutput(self.rewarder)}
            if outputs is None
            else outputs,
        )
        return SimpleNamespace(
            session=self.session, mxbi=mxbi, publish_trial=self.publish, timer=Mock()
        )

    def trial(self, scenes: Experiment, context: SimpleNamespace):
        """Start the next trial of the animal's stage at the current time."""
        animal = self.session.require_current_animal()
        with patch("mxbiflow.context._current_mxbiflow", context):
            scene = machine_scenes(scenes)[animal.current_stage_name]()
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
        self.aplayer.play.assert_called_once()
        samples = self.aplayer.play.call_args.args[0].samples[:, 0]
        # A 100 ms tone, a 100 ms gap, and the train is cut at the sound's 250 ms.
        self.assertEqual(len(samples), 250 * 8)
        self.assertTrue(samples[:800].any() and samples[1600:].any())
        self.assertFalse(samples[800:1600].any())
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
            {"animal": "a", "trial": 1, "stage": "touch", "level": 0},
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

    def test_a_files_stage_counts_its_trials_and_keeps_the_animal_where_it_is(
        self,
    ) -> None:
        scenes = experiment(stage("touch"))
        context = self.context(scenes)
        for _ in range(3):
            start = self.now
            scene = self.trial(scenes, context)
            self.touch(scene, (150, 20), at=start + 10)
            self.now = start + 100
            scene.update(0)

        # A file has the trial, not how an animal moves between levels.
        self.assertEqual([r["action"] for r in self.records("touch")], ["none"] * 3)
        state = self.session.require_current_animal().current_stage
        self.assertEqual((state.level_counted, state.level_correct), (3, 3))

    def test_a_trial_the_animal_leaves_is_recorded_but_not_counted(self) -> None:
        scenes = experiment(stage("touch"))
        scene = self.trial(scenes, self.context(scenes))

        self.now = 40
        scene.quit()

        self.assertFalse(scene.running)
        (record,) = self.records("touch")
        self.assertEqual(record["outcome"], "none")
        self.assertEqual(record["events"][-1], {"t": 40, "text": "trial stopped"})
        stage_state = self.session.require_current_animal().current_stage
        self.assertEqual(
            (stage_state.level_trial_id, stage_state.level_counted), (1, 0)
        )

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
        scenes = experiment(stage("touch", screen=(100, 200), target=(0.2, 0.75)))
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
            "x": 0.75,
            "y": 0.2,
            "size": "fraction",
            "width": 0.1,
            "height": 0.1,
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

    def test_a_gpio_edge_keeps_the_time_it_happened(self) -> None:
        scenes = experiment(stage("touch"))
        beam = Mock()
        beam.level.return_value = True
        beam.changes.return_value = []
        scene = self.trial(scenes, self.context(scenes, inputs={"beam": beam}))

        # The beam fell at 12 ms; the frame that reads it is at 30 ms.
        beam.changes.return_value = [(0.012, False)]
        self.now = 30
        scene.update(0)

        self.assertEqual(
            self.records("touch")[0]["events"][-2:],
            [{"t": 12, "text": "beam.fall → exit"}, {"t": 12, "text": "trial ends"}],
        )

    def test_touches_and_edges_of_a_frame_are_handled_in_order(self) -> None:
        scenes = experiment(stage("touch"))
        beam = Mock()
        beam.level.return_value = True
        beam.changes.return_value = []
        scene = self.trial(scenes, self.context(scenes, inputs={"beam": beam}))

        # The touch at 10 ms comes before the beam's fall at 20 ms.
        self.now = 10
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=(150, 20)))
        beam.changes.return_value = [(0.020, False)]
        self.now = 30
        scene.update(0)

        self.assertEqual(
            [entry["state"] for entry in self.records_after(scene)["states"]],
            ["choice", "reward"],
        )

    def records_after(self, scene: Any) -> dict[str, Any]:
        """Let the trial run out and return its record."""
        self.now += 100
        scene.update(0)
        return self.records("touch")[0]

    def test_an_unwired_channel_stops_the_run_with_its_name(self) -> None:
        scenes = experiment(stage("touch"))
        context = self.context(scenes, inputs={}, outputs={})

        with self.assertRaisesRegex(ValueError, 'input "beam", output "reward"'):
            self.trial(scenes, context)

    def test_the_rig_screen_counts_not_the_experiment_reference(self) -> None:
        # Laid out on a 400×200 reference; this rig's screen is 200×100.
        scenes = experiment(stage("touch", screen=(400, 200)))
        scene = self.trial(scenes, self.context(scenes))
        screen = Surface((200, 100))

        scene.draw(screen)

        self.assertEqual(screen.get_at((150, 20)), (255, 0, 0, 255))

    def test_a_stimulus_that_does_not_fit_the_rig_screen_fails(self) -> None:
        scenes = experiment(stage("touch", size=150))

        with self.assertRaisesRegex(ValueError, '"target" does not fit'):
            self.trial(scenes, self.context(scenes))

    def test_a_position_outside_the_screen_fails(self) -> None:
        scenes = experiment(stage("touch", target=(1.2, 0.5)))

        with self.assertRaisesRegex(ValueError, '"target" is outside the screen'):
            self.trial(scenes, self.context(scenes))
