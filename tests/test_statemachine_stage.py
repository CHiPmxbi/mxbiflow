import json
import tempfile
import unittest
from collections.abc import Sequence
from enum import StrEnum, auto
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from pydantic import BaseModel
from pygame import MOUSEBUTTONDOWN, Event

from mxbiflow.driver import MXBIModel
from mxbiflow.driver.channels import RewarderOutput
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.scene.settlement import SettlementAction
from mxbiflow.statemachine.runner import Trial
from mxbiflow.statemachine.scene import Hook, MachineScene, Rule
from mxbiflow.statemachine.stage import (
    EXIT,
    Clear,
    CountRule,
    Host,
    Level,
    On,
    Outcome,
    Rect,
    ScreenTouch,
    Show,
    Size,
    Stage,
    State,
    StateParam,
    Time,
    Timeout,
    Touch,
    TrialParams,
    stage_scenes,
)


class S(StrEnum):
    WAIT = auto()
    JUDGE = auto()
    FAST = auto()
    SLOW = auto()
    MISS = auto()


class Out(StrEnum):
    REWARD = auto()


class Stim(StrEnum):
    TARGET = auto()


class Verdict(StrEnum):
    FAST = auto()
    SLOW = auto()


class Params(TrialParams):
    reward_ms: Time = 50
    target_x: float = 0.75


class Extra(BaseModel):
    latency_ms: float


p = Params.refs()


def touch_stage(
    *,
    on_trial: Sequence[Hook] = (),
    on_judge: Hook | None = None,
    rule: Rule | CountRule | None = None,
    levels: Sequence[Level] = (Level(name="near", values={p.reward_ms: 80}),),
) -> Stage:
    """Touch the target: a fast touch is rewarded longer than a slow one."""
    return Stage(
        name="touch",
        params=Params,
        outputs=Out,
        screen=(200, 100),
        stimuli=[
            Rect(
                name=Stim.TARGET,
                x=p.target_x,
                y=0.2,
                width=20,
                height=20,
                size=Size.px,
                color="#ff0000",
            )
        ],
        states=[
            State(name=S.WAIT, timeout_ms=1000, on_entry=[Show(Stim.TARGET)]),
            State(name=S.JUDGE, on_entry=[Clear()]),
            State(
                name=S.FAST,
                timeout_ms=p.reward_ms,
                hold=[Out.REWARD],
                outcome=Outcome.correct,
            ),
            State(
                name=S.SLOW, timeout_ms=10, hold=[Out.REWARD], outcome=Outcome.correct
            ),
            State(
                name=S.MISS,
                timeout_ms=10,
                on_entry=[Clear()],
                outcome=Outcome.incorrect,
            ),
        ],
        transitions=[
            On(source=S.WAIT, event=Touch(Stim.TARGET), target=S.JUDGE),
            On(source=S.WAIT, event=ScreenTouch(), target=S.MISS),
            On(source=S.WAIT, event=Timeout(), target=S.MISS),
            On(source=S.JUDGE, event=Host(Verdict.FAST), target=S.FAST),
            On(source=S.JUDGE, event=Host(Verdict.SLOW), target=S.SLOW),
            *(
                On(source=state, event=Timeout(), target=EXIT)
                for state in (S.FAST, S.SLOW, S.MISS)
            ),
        ],
        levels=levels,
        rule=CountRule(2) if rule is None else rule,
        on_trial=on_trial,
        on_enter={} if on_judge is None else {S.JUDGE: on_judge},
    )


def always_fast(scene: MachineScene) -> None:
    scene.fire(Verdict.FAST)


class StageTests(unittest.TestCase):
    def test_the_built_machine_runs_as_data(self) -> None:
        stage, _ = touch_stage().build()
        trial = Trial(stage.machine, screen=(200, 100))

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
        stage = Stage(
            name="lost",
            outputs=Out,
            states=[
                State(name=S.WAIT, on_entry=[Show("ghost")]),
                State(name=S.FAST, hold=["laser"]),
            ],
            transitions=[
                On(source=S.WAIT, event=Host(Verdict.SLOW), target="nowhere"),
                On(source="nobody", event=Timeout(), target=EXIT),
            ],
            on_enter={"gone": always_fast},
        )

        with self.assertRaises(ValueError) as raised:
            stage.build()

        message = str(raised.exception)
        for part in (
            'wait: no state "nowhere"',
            'fast: no output "laser"',
            'wait: show "ghost" does not exist',
            'a transition from "nobody", which is no state or group',
            'no state "gone"',
        ):
            self.assertIn(part, message)

    def test_a_parameter_that_is_not_one_is_refused_where_it_is_written(self) -> None:
        with self.assertRaisesRegex(AttributeError, "no parameter rewardms"):
            _ = p.rewardms  # pyright: ignore[reportAttributeAccessIssue]

    def test_defaults_known_when_the_stage_is_made_are_an_instance(self) -> None:
        class Timed(TrialParams):
            wait_ms: Time
            after: StateParam[S]

        stage = Stage(
            name="timed",
            params=Timed,
            defaults=Timed(wait_ms=300, after=S.FAST),
            states=[
                State(name=S.WAIT, timeout_ms=Timed.refs().wait_ms),
                State(name=S.FAST),
            ],
            transitions=[On(source=S.WAIT, event=Timeout(), target=Timed.refs().after)],
        )

        parameters = stage.build()[0].machine.parameters
        self.assertEqual(
            [(x.name, x.type, x.default) for x in parameters],
            [("wait_ms", "time", 300), ("after", "state", "fast")],
        )
        with self.assertRaisesRegex(ValueError, "parameter wait_ms needs a default"):
            Stage(name="none", params=Timed, states=[State(name=S.WAIT)]).build()

    def test_a_parameter_whose_type_does_not_say_what_it_is_is_refused(self) -> None:
        class Vague(TrialParams):
            after: S = S.FAST

        stage = Stage(name="vague", params=Vague, states=[State(name=S.FAST)])
        with self.assertRaisesRegex(ValueError, "parameter after: its type does not"):
            stage.build()

    def test_plain_strings_name_things_as_enum_members_do(self) -> None:
        stage = Stage(
            name="plain",
            states=[State(name="wait", timeout_ms=10)],
            transitions=[On(source="wait", event=Timeout(), target=EXIT)],
        )
        data, _ = stage.build()
        self.assertEqual(data.machine.states[0].transitions[0].target, "exit")


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
                aplayer=Mock(
                    frequency_response_table=None, prepare=lambda sound: sound
                ),
                inputs={},
                outputs={"reward": RewarderOutput(self.rewarder)},
            ),
            publish_trial=Mock(),
            timer=Mock(),
        )

    def run_trial(self, stage: Stage, touch_at: int) -> dict[str, Any]:
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
        def judge(scene: MachineScene) -> None:
            latency = scene.now_ms
            scene.note(Extra(latency_ms=latency))
            scene.fire(Verdict.FAST if latency < 300 else Verdict.SLOW)

        stage = touch_stage(on_judge=judge)

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

    def test_a_hook_sets_and_reads_the_values_of_the_trial(self) -> None:
        seen: list[Params] = []

        def move_target(scene: MachineScene) -> None:
            # The target is elsewhere: the touch at its default place misses.
            scene.set(p.target_x, 0.25)
            seen.append(scene.params(Params))

        stage = touch_stage(on_trial=[move_target], on_judge=always_fast)

        record = self.run_trial(stage, touch_at=100)

        self.assertEqual(seen, [Params(reward_ms=80, target_x=0.25)])
        self.assertEqual(record["values"]["target_x"], 0.25)
        self.assertEqual(record["outcome"], "incorrect")

    def test_a_rule_in_python_decides_whether_the_animal_moves(self) -> None:
        asked: list[tuple[Outcome | None, int]] = []

        def rule(scene: MachineScene, outcome: Outcome | None) -> SettlementAction:
            asked.append((outcome, scene.info.level))
            return (
                SettlementAction.LEVEL_UP if len(asked) == 2 else SettlementAction.NONE
            )

        stage = touch_stage(
            on_judge=always_fast,
            rule=rule,
            levels=[
                Level(name="near", values={p.reward_ms: 80}),
                Level(name="far", values={p.reward_ms: 20}),
            ],
        )

        first = self.run_trial(stage, touch_at=100)
        second = self.run_trial(stage, touch_at=100)

        self.assertEqual((first["action"], second["action"]), ("none", "level up"))
        self.assertEqual(asked, [(Outcome.correct, 1), (Outcome.correct, 1)])
        self.assertEqual(self.session.require_current_animal().current_stage.level, 2)

    def test_a_rule_that_decides_a_move_that_does_not_exist_stops_the_run(self) -> None:
        stage = touch_stage(
            on_judge=always_fast, rule=lambda scene, outcome: SettlementAction.LEVEL_UP
        )

        with self.assertRaisesRegex(ValueError, '"level up", which is not possible'):
            self.run_trial(stage, touch_at=100)

    def test_a_trial_left_after_its_outcome_is_known_is_settled(self) -> None:
        stage = touch_stage(on_judge=always_fast)
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
