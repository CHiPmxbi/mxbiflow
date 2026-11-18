import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from pygame import MOUSEBUTTONDOWN, Event

from mxbiflow.driver import MXBIModel
from mxbiflow.driver.channels import RewarderOutput
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.statemachine.builder import (
    EXIT,
    StageBuilder,
    clear,
    show,
    stage_scenes,
)
from mxbiflow.statemachine.host import Action
from mxbiflow.statemachine.runner import Trial
from mxbiflow.statemachine.scene import MachineScene


def touch_stage() -> StageBuilder:
    """Touch the target: a fast touch is rewarded longer than a slow one."""
    stage = StageBuilder("touch", outputs=["reward"], screen=(200, 100))
    reward_ms = stage.add_time("reward_ms", 50)
    target_x = stage.add_number("target_x", 0.75)
    target = stage.add_rect(
        "target", x=target_x, y=0.2, width=20, height=20, size="px", color="#ff0000"
    )
    stage.add_state("wait", on_entry=[show(target)], timeout=1000)
    stage.add_state("judge", on_entry=[clear()])
    stage.add_state("fast", hold=["reward"], timeout=reward_ms)
    stage.add_state("slow", hold=["reward"], timeout=10)
    stage.add_state("miss", on_entry=[clear()], timeout=10)
    stage.add_transition("wait", f"{target}.touch", "judge")
    stage.add_transition("wait", "screen.touch", "miss")
    stage.add_transition("wait", "timeout", "miss")
    stage.add_transition("judge", "host.fast", "fast")
    stage.add_transition("judge", "host.slow", "slow")
    for state in ("fast", "slow", "miss"):
        stage.add_transition(state, "timeout", EXIT)
    stage.set_outcome("fast", "correct")
    stage.set_outcome("slow", "correct")
    stage.set_outcome("miss", "incorrect")
    stage.add_level("near", {"reward_ms": 80})
    stage.set_count_rule(correct=2)
    return stage


class StageBuilderTests(unittest.TestCase):
    def test_the_built_machine_runs_as_data(self) -> None:
        stage, _ = touch_stage().build()
        trial = Trial(stage.machine)

        trial.touch(150, 20, 100)
        self.assertEqual(trial.state, "judge")
        trial.host("fast", 120)
        self.assertEqual((trial.state, trial.held()), ("fast", {"reward"}))
        trial.advance(200)

        self.assertIsNone(trial.state)
        self.assertEqual(
            [visit.state for visit in trial.visited], ["wait", "judge", "fast"]
        )
        self.assertEqual(stage.levels[0].values, {"reward_ms": 80})

    def test_a_name_that_leads_nowhere_is_refused_with_its_place(self) -> None:
        stage = touch_stage()
        stage.add_transition("wait", "host.skip", "nowhere")
        stage.add_state("lit", hold=["laser"], on_entry=[show("ghost")])
        stage.on_enter("gone", lambda scene: None)

        with self.assertRaises(ValueError) as raised:
            stage.build()

        message = str(raised.exception)
        for part in (
            'wait: no state "nowhere"',
            'lit: no output "laser"',
            'lit: show "ghost" does not exist',
            'no state "gone"',
        ):
            self.assertIn(part, message)

    def test_a_transition_from_an_unknown_state_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, 'no state or group "ghost"'):
            touch_stage().add_transition("ghost", "timeout", EXIT)


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = 0
        patcher = patch(
            "mxbiflow.statemachine.scene.monotonic", side_effect=lambda: self.now / 1000
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        config = AnimalConfig(name="a", stage="touch", level=1)
        animal = Animal(
            config=config,
            current_stage_name="touch",
            stages={"touch": StageState(stage_name="touch", level=1)},
        )
        self.session = Session(
            config=SessionConfig(unknown_animal_as="a", animals=(config,)),
            mxbi_config=MXBIModel(),
            state=SessionState(animals={"a": animal}),
        )
        self.session.start(Path(directory.name))
        self.session.set_current_animal("a")
        self.rewarder = Mock()
        self.context = SimpleNamespace(
            session=self.session,
            mxbi=SimpleNamespace(
                screen_size=SimpleNamespace(width=200, height=100),
                aplayer=Mock(frequency_response_table=None),
                inputs={},
                outputs={"reward": RewarderOutput(self.rewarder)},
            ),
            publish_trial=Mock(),
            timer=Mock(),
        )

    def run_trial(self, stage: StageBuilder, touch_at: int) -> dict[str, Any]:
        """One trial touched at the target's default place; returns its record."""
        with patch("mxbiflow.context._current_mxbiflow", self.context):
            scene = stage_scenes(stage)["touch"]()
        self.now = 0
        scene.start()
        self.now = touch_at
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=(150, 20)))
        scene.update(0)
        self.now = touch_at + 500
        scene.update(0)
        self.assertFalse(scene.running)
        path = self.session.absolute_animal_data_path("a") / "touch" / "result.jsonl"
        return json.loads(path.read_text().splitlines()[-1])

    def test_a_hook_judges_the_touch_and_sends_the_machine_its_verdict(self) -> None:
        stage = touch_stage()

        def judge(scene: MachineScene) -> None:
            latency = scene.now
            scene.note("latency_ms", latency)
            scene.fire("fast" if latency < 300 else "slow")

        stage.on_enter("judge", judge)

        fast = self.run_trial(stage, touch_at=100)
        slow = self.run_trial(stage, touch_at=400)

        self.assertEqual(
            [entry["state"] for entry in fast["states"]], ["wait", "judge", "fast"]
        )
        self.assertEqual(fast["extra"], {"latency_ms": 100})
        self.assertEqual(
            [entry["state"] for entry in slow["states"]], ["wait", "judge", "slow"]
        )
        self.assertEqual((fast["outcome"], slow["outcome"]), ("correct", "correct"))
        # Two correct trials: the count rule has nowhere to go and stays.
        self.assertEqual(slow["action"], "none")

    def test_a_hook_sets_the_values_of_the_trial_before_it_starts(self) -> None:
        stage = touch_stage()
        stage.on_enter("judge", lambda scene: scene.fire("fast"))

        @stage.on_trial
        def move_target(scene: MachineScene) -> None:
            # The target is elsewhere: the touch at its default place misses.
            scene.values["target_x"] = 0.25

        record = self.run_trial(stage, touch_at=100)

        self.assertEqual(record["values"]["target_x"], 0.25)
        self.assertEqual(record["values"]["reward_ms"], 80)
        self.assertEqual(record["outcome"], "incorrect")

    def test_a_rule_in_python_decides_whether_the_animal_moves(self) -> None:
        stage = touch_stage()
        stage.add_level("far", {"reward_ms": 20})
        stage.on_enter("judge", lambda scene: scene.fire("fast"))
        asked: list[tuple[str, int]] = []

        def rule(scene: MachineScene, outcome: str) -> Action:
            asked.append((outcome, scene.info.level))
            return "level up" if len(asked) == 2 else "none"

        stage.set_rule(rule)

        first = self.run_trial(stage, touch_at=100)
        second = self.run_trial(stage, touch_at=100)

        # The stage's own rule (two correct trials) is not asked.
        self.assertEqual((first["action"], second["action"]), ("none", "level up"))
        self.assertEqual(asked, [("correct", 1), ("correct", 1)])
        self.assertEqual(self.session.require_current_animal().current_stage.level, 2)

    def test_a_rule_that_decides_a_move_that_does_not_exist_stops_the_run(self) -> None:
        stage = touch_stage()
        stage.on_enter("judge", lambda scene: scene.fire("fast"))
        stage.set_rule(lambda scene, outcome: "level up")

        with self.assertRaisesRegex(ValueError, '"level up", which is not possible'):
            self.run_trial(stage, touch_at=100)

    def test_a_trial_left_after_its_outcome_is_known_is_settled(self) -> None:
        stage = touch_stage()
        stage.on_enter("judge", lambda scene: scene.fire("fast"))
        with patch("mxbiflow.context._current_mxbiflow", self.context):
            scene = stage_scenes(stage)["touch"]()
        scene.start()
        self.now = 100
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=(150, 20)))
        scene.update(0)
        scene.update(0)

        # The animal leaves while the reward runs.
        self.now = 120
        scene.quit()

        assert isinstance(scene, MachineScene)
        self.assertFalse(scene.aborted)
        state = self.session.require_current_animal().current_stage
        self.assertEqual((state.level_counted, state.level_correct), (1, 1))
