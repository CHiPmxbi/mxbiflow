"""A machine written in Python, and a stage class that runs it."""

import json
import tempfile
import unittest
from enum import StrEnum, auto
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import Mock, patch

from pydantic import BaseModel
from pygame import MOUSEBUTTONDOWN, Event

from mxbiflow.driver import MXBIModel
from mxbiflow.driver.audioplayer import AudioFormat
from mxbiflow.driver.channels import RewarderOutput
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.scene.settlement import SettlementAction
from mxbiflow.statemachine.host import TrialRecord
from mxbiflow.statemachine.machine import (
    EXIT,
    Cancel,
    Clear,
    Host,
    Machine,
    On,
    Outcome,
    Play,
    Rect,
    ScreenTouch,
    SetLow,
    Show,
    Size,
    State,
    StateParam,
    StimulusParam,
    Time,
    Timeout,
    Tones,
    Touch,
    TrialParams,
)
from mxbiflow.statemachine.models import ParamRef
from mxbiflow.statemachine.runner import Edge, Trial
from mxbiflow.statemachine.scene import MachineTrial, on_enter
from mxbiflow.statemachine.stage import Stage


class S(StrEnum):
    WAIT = auto()
    JUDGE = auto()
    FAST = auto()
    SLOW = auto()
    MISS = auto()


class Out(StrEnum):
    REWARD = auto()


class Stim(StrEnum):
    LEFT = auto()
    RIGHT = auto()
    LOW = auto()
    HIGH = auto()


class Verdict(StrEnum):
    FAST = auto()
    SLOW = auto()


class Params(TrialParams):
    reward_ms: Time = 50
    target: StimulusParam[Stim] = Stim.RIGHT
    sound: StimulusParam[Stim] = Stim.LOW
    hz: float = 1000
    tone_ms: Time = 100


class Extra(BaseModel):
    latency_ms: float


p = Params.refs()
# A touch is the event of the stimulus touched: each target has its own transition.
PLACES = {Stim.LEFT: 0.25, Stim.RIGHT: 0.75}
MACHINE = Machine(
    params=Params,
    outputs=Out,
    screen=(200, 100),
    stimuli=[
        *(
            Rect(
                name=name,
                x=x,
                y=0.2,
                width=20,
                height=20,
                size=Size.px,
                color="#ff0000",
            )
            for name, x in PLACES.items()
        ),
        Tones(name=Stim.LOW, tones=[(p.hz, p.tone_ms)], duration_ms=p.tone_ms),
        Tones(name=Stim.HIGH, tones=[(8000, 50)], duration_ms=50),
    ],
    states=[
        State(name=S.WAIT, timeout_ms=1000, on_entry=[Show(p.target), Play(p.sound)]),
        State(name=S.JUDGE, on_entry=[Clear()]),
        State(
            name=S.FAST,
            timeout_ms=p.reward_ms,
            hold=[Out.REWARD],
            outcome=Outcome.correct,
        ),
        State(name=S.SLOW, timeout_ms=10, hold=[Out.REWARD], outcome=Outcome.correct),
        State(
            name=S.MISS, timeout_ms=10, on_entry=[Clear()], outcome=Outcome.incorrect
        ),
    ],
    transitions=[
        *(On(source=S.WAIT, event=Touch(name), target=S.JUDGE) for name in PLACES),
        On(source=S.WAIT, event=ScreenTouch(), target=S.MISS),
        On(source=S.WAIT, event=Timeout(), target=S.MISS),
        On(source=S.JUDGE, event=Host(Verdict.FAST), target=S.FAST),
        On(source=S.JUDGE, event=Host(Verdict.SLOW), target=S.SLOW),
        *(
            On(source=state, event=Timeout(), target=EXIT)
            for state in (S.FAST, S.SLOW, S.MISS)
        ),
    ],
)


class TouchTrial(MachineTrial[Params]):
    """Touch the target: a fast touch is rewarded longer than a slow one."""

    def machine(self) -> Machine:
        return MACHINE

    @on_enter(S.JUDGE)
    def judge(self) -> None:
        latency_ms = self.now_ms
        self.note(Extra(latency_ms=latency_ms))
        self.fire(Verdict.FAST if latency_ms < 300 else Verdict.SLOW)


class Touching(Stage[Params]):
    """Gives the trials the tests' values; up after two correct trials at a level."""

    trial = TouchTrial
    level_table: ClassVar[dict[str, list[int]]] = {"default": [1, 2]}
    #: The values of the next trials, for the tests to set.
    next_params: ClassVar[Params] = Params()

    @classmethod
    def name(cls) -> str:
        return "touch"

    def __init__(self, *, session: Session, animal: Animal) -> None:
        super().__init__(session=session, animal=animal)
        self.decided: list[TrialRecord] = []

    def next_trial(self) -> Params:
        return self.next_params

    def decide(self, record: TrialRecord) -> SettlementAction:
        self.decided.append(record)
        correct = sum(
            r.outcome == Outcome.correct and r.level == record.level
            for r in self.decided
        )
        is_up = correct >= 2 and record.level < 2
        return SettlementAction.LEVEL_UP if is_up else SettlementAction.NONE


class MachineTests(unittest.TestCase):
    def test_the_built_machine_runs_as_data(self) -> None:
        stage = MACHINE.build("touch")
        trial = Trial(stage.machine, screen=(200, 100))

        trial.touch(150, 20, 100)
        self.assertEqual(trial.state, "judge")
        trial.host("fast", 120)
        self.assertEqual((trial.state, trial.high()), ("fast", {"reward"}))
        trial.advance(200)

        self.assertIsNone(trial.state)
        self.assertEqual(
            trial.changes, [Edge(120, "reward", True), Edge(170, "reward", False)]
        )
        self.assertEqual(
            [visit.state for visit in trial.visited], ["wait", "judge", "fast"]
        )
        self.assertEqual(stage.name, "touch")
        self.assertEqual(stage.outcomes["miss"], Outcome.incorrect)

    def test_a_name_that_leads_nowhere_is_refused_with_its_place(self) -> None:
        machine = Machine(
            outputs=Out,
            states=[
                State(name=S.WAIT, on_entry=[Show("ghost")]),
                State(name=S.FAST, hold=["laser"]),
            ],
            transitions=[
                On(source=S.WAIT, event=Host(Verdict.SLOW), target="nowhere"),
                On(source="nobody", event=Timeout(), target=EXIT),
                On(source=S.FAST, event=Timeout(), target=EXIT),
            ],
        )

        with self.assertRaises(ValueError) as raised:
            machine.build("lost")

        message = str(raised.exception)
        for part in (
            'stage "lost"',
            'wait: no state "nowhere"',
            'fast: high "laser" does not exist',
            "fast: a timeout without timeout_ms",
            'wait: show "ghost" does not exist',
            'a transition from "nobody", which is no state or group',
        ):
            self.assertIn(part, message)

    def test_shortcuts_are_written_out_as_instructions(self) -> None:
        machine = Machine(
            outputs=Out,
            states=[
                State(
                    name=S.WAIT,
                    timeout_ms=30,
                    hold=[Out.REWARD],
                    on_entry=[Clear()],
                    on_exit=[Cancel(Out.REWARD)],
                )
            ],
            transitions=[
                On(source=S.WAIT, event=Timeout(), target=EXIT),
                On(
                    source=S.WAIT,
                    event=ScreenTouch(),
                    actions=[SetLow(output=Out.REWARD, after_ms=5)],
                ),
            ],
        )

        built = machine.build("short").machine
        state = built.states[0].model_dump(mode="json", by_alias=True)

        self.assertEqual(
            [
                (t.name, t.time.root)
                for t in built.timers
                if not isinstance(t.time, ParamRef)
            ],
            [("wait_time", 30)],
        )
        self.assertEqual(
            state["onEntry"],
            [
                {"high": "reward", "after": None},
                {"start": "wait_time"},
                {"clear": True},
            ],
        )
        self.assertEqual(
            state["onExit"],
            [
                {"cancel": "reward"},
                {"stop": "wait_time"},
                {"low": "reward", "after": None},
            ],
        )
        self.assertEqual(
            state["transitions"],
            [
                {"event": "wait_time.done", "target": "exit", "actions": []},
                {
                    "event": "screen.touch",
                    "target": None,
                    "actions": [{"low": "reward", "after": 5}],
                },
            ],
        )

    def test_a_transition_that_does_nothing_is_refused(self) -> None:
        machine = Machine(
            states=[State(name=S.WAIT)],
            transitions=[On(source=S.WAIT, event=ScreenTouch())],
        )

        with self.assertRaisesRegex(
            ValueError, 'wait: "screen.touch" has no target and does nothing'
        ):
            machine.build("idle")

    def test_an_event_with_two_transitions_in_one_state_is_refused(self) -> None:
        machine = Machine(
            states=[State(name=S.WAIT), State(name=S.FAST), State(name=S.SLOW)],
            transitions=[
                On(source=S.WAIT, event=ScreenTouch(), target=S.FAST),
                On(source=S.WAIT, event=ScreenTouch(), target=S.SLOW),
            ],
        )

        # The first would always win, whatever the second was meant for.
        with self.assertRaisesRegex(
            ValueError, 'wait: "screen.touch" has more than one transition'
        ):
            machine.build("twice")

    def test_a_parameter_that_is_not_one_is_refused_where_it_is_written(self) -> None:
        with self.assertRaisesRegex(AttributeError, "no parameter rewardms"):
            _ = p.rewardms  # pyright: ignore[reportAttributeAccessIssue]

    def test_defaults_known_when_the_machine_is_made_are_an_instance(self) -> None:
        class Timed(TrialParams):
            wait_ms: Time
            after: StateParam[S]

        machine = Machine(
            params=Timed,
            defaults=Timed(wait_ms=300, after=S.FAST),
            states=[
                State(name=S.WAIT, timeout_ms=Timed.refs().wait_ms),
                State(name=S.FAST),
            ],
            transitions=[On(source=S.WAIT, event=Timeout(), target=Timed.refs().after)],
        )

        parameters = machine.build("timed").machine.parameters
        self.assertEqual(
            [(x.name, x.type, x.default) for x in parameters],
            [("wait_ms", "time", 300), ("after", "state", "fast")],
        )
        with self.assertRaisesRegex(ValueError, "parameter wait_ms needs a default"):
            Machine(params=Timed, states=[State(name=S.WAIT)]).build("none")

    def test_a_parameter_whose_type_does_not_say_what_it_is_is_refused(self) -> None:
        class Vague(TrialParams):
            after: S = S.FAST

        machine = Machine(params=Vague, states=[State(name=S.FAST)])
        with self.assertRaisesRegex(ValueError, "parameter after: its type does not"):
            machine.build("vague")

    def test_a_stimulus_parameter_both_shown_and_played_is_refused(self) -> None:
        class Both(TrialParams):
            either: StimulusParam[Stim] = Stim.LEFT

        either = Both.refs().either
        machine = Machine(
            params=Both,
            stimuli=[
                Rect(
                    name=Stim.LEFT, x=0.5, y=0.5, width=0.2, height=0.2, color="#fff000"
                )
            ],
            states=[State(name=S.WAIT, on_entry=[Show(either), Play(either)])],
        )
        with self.assertRaisesRegex(ValueError, "either is both shown and played"):
            machine.build("both")

    def test_plain_strings_name_things_as_enum_members_do(self) -> None:
        machine = Machine(
            states=[State(name="wait", timeout_ms=10)],
            transitions=[On(source="wait", event=Timeout(), target=EXIT)],
        )
        data = machine.build("plain")
        self.assertEqual(data.machine.states[0].transitions[0].target, "exit")

    def test_the_sound_a_trial_names_is_played_at_the_trials_length(self) -> None:
        stage = MACHINE.build("touch")
        values = Params(sound=Stim.LOW, tone_ms=240).model_dump(mode="json")

        trial = Trial(stage.machine, values=values, screen=(200, 100))

        self.assertEqual((trial.shown, trial.sounds), (["right"], {"low": 240}))
        self.assertEqual(
            [t.event for t in stage.machine.states[0].transitions][:2],
            ["left.touch", "right.touch"],
        )


class Run(SimpleNamespace):
    """What stands in for the run's context; hashable, as the context is."""

    def __hash__(self) -> int:
        return id(self)


class MachineTrialTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = 0
        patcher = patch(
            "mxbiflow.statemachine.scene.monotonic", side_effect=lambda: self.now / 1000
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, Touching, "next_params", Params())

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
        self.aplayer = Mock(
            frequency_response_table=None,
            format=AudioFormat(sample_rate_hz=8000, channels=1),
            prepare=lambda sound: sound,
        )
        self.context = Run(
            session=self.session,
            mxbi=SimpleNamespace(
                screen_size=SimpleNamespace(width=200, height=100),
                aplayer=self.aplayer,
                inputs={},
                outputs={"reward": RewarderOutput(self.rewarder)},
            ),
            publish_trial=Mock(),
            timer=Mock(),
        )

    def start(self, stage: type[Stage[Any]] = Touching) -> Any:
        with patch("mxbiflow.context._current_mxbiflow", self.context):
            scene = stage.scene()()
        self.started = self.now
        scene.start()
        return scene

    def run_trial(
        self, touch: tuple[int, int] = (150, 20), after: int = 100
    ) -> dict[str, Any]:
        """One trial with a touch ``after`` ms into it; returns its record."""
        scene = self.start()
        self.now = self.started + after
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=touch))
        scene.update(0)
        self.now += 500
        scene.update(0)
        self.assertFalse(scene.running)
        path = self.session.absolute_animal_data_path("a") / "touch" / "result.jsonl"
        return json.loads(path.read_text().splitlines()[-1])

    def test_a_method_judges_the_touch_and_sends_the_machine_its_verdict(self) -> None:
        fast = self.run_trial(after=100)
        slow = self.run_trial(after=400)

        self.assertEqual(
            [entry["state"] for entry in fast["states"]], ["wait", "judge", "fast"]
        )
        self.assertEqual(fast["extra"], {"latency_ms": 100})
        self.assertEqual(
            [entry["state"] for entry in slow["states"]], ["wait", "judge", "slow"]
        )
        self.assertEqual((fast["outcome"], slow["outcome"]), ("correct", "correct"))

    def test_the_stage_gives_each_trial_its_values(self) -> None:
        # The target is on the left: a touch at its default place misses.
        Touching.next_params = Params(reward_ms=80, target=Stim.LEFT)

        missed = self.run_trial(touch=(150, 20))
        hit = self.run_trial(touch=(50, 20))

        self.assertEqual(missed["outcome"], "incorrect")
        self.assertEqual(hit["outcome"], "correct")
        self.assertEqual(
            hit["values"],
            {
                "reward_ms": 80,
                "target": "left",
                "sound": "low",
                "hz": 1000,
                "tone_ms": 100,
            },
        )

    def test_the_stage_reads_its_values_back_as_the_model(self) -> None:
        Touching.next_params = Params(reward_ms=80)

        scene = self.start()

        self.assertEqual(scene.given, Params(reward_ms=80))
        self.assertIsNone(scene.outcome)

    def test_the_stage_reads_each_record_and_moves_the_animal(self) -> None:
        actions = [self.run_trial()["action"] for _ in range(2)]

        self.assertEqual(actions, ["none", "level up"])
        self.assertEqual(self.session.require_current_animal().current_stage.level, 2)

    def test_a_stage_decides_from_the_record_before_it_is_written(self) -> None:
        asked: list[tuple[str, str, int]] = []

        class Picky(Touching):
            def decide(self, record: TrialRecord) -> SettlementAction:
                asked.append((record.outcome, record.action, self.level))
                return SettlementAction.LEVEL_UP

        scene = self.start(Picky)
        self.now = 100
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=(150, 20)))
        scene.update(0)
        self.now = 600
        scene.update(0)

        self.assertEqual(asked, [("correct", "none", 1)])
        self.assertEqual(self.session.require_current_animal().current_stage.level, 2)

    def test_a_value_the_machine_cannot_take_stops_the_run(self) -> None:
        # A sound where a picture is shown.
        Touching.next_params = Params(target=Stim.LOW)

        with self.assertRaisesRegex(
            ValueError,
            'the values of the trial: target: "low" is not a stimulus on the',
        ):
            self.start()

    def test_a_method_for_a_state_the_machine_has_not_stops_the_run(self) -> None:
        class LostTrial(TouchTrial):
            @on_enter("gone")
            def never(self) -> None: ...

        class Lost(Touching):
            trial = LostTrial

        with self.assertRaisesRegex(ValueError, r"on_enter of no state: \['gone'\]"):
            self.start(Lost)

    def test_a_trial_left_after_its_outcome_is_known_is_settled(self) -> None:
        scene = self.start()
        self.now = 100
        scene.handle_event(Event(MOUSEBUTTONDOWN, button=1, pos=(150, 20)))
        scene.update(0)
        scene.update(0)

        # The animal leaves while the reward runs.
        self.now = 120
        scene.quit()

        self.assertFalse(scene.aborted)
        self.assertEqual([r.outcome for r in scene.stage.decided], ["correct"])

    def test_an_animal_keeps_its_stage_object_for_the_run(self) -> None:
        first = self.start()
        first.quit()
        second = self.start()

        self.assertIs(first.stage, second.stage)
        self.assertIs(first.stage.animal, self.session.require_current_animal())

    def test_a_trial_without_its_stage_is_refused(self) -> None:
        with (
            patch("mxbiflow.context._current_mxbiflow", self.context),
            self.assertRaisesRegex(TypeError, r"register its stage's scene\(\)"),
        ):
            TouchTrial()

    def test_a_machine_is_built_once_for_its_trials(self) -> None:
        real = Machine.build
        builds: list[str] = []

        def build(machine: Machine, name: str) -> Any:
            builds.append(name)
            return real(machine, name)

        MachineTrial._built.clear()  # pyright: ignore[reportPrivateUsage]
        with patch.object(Machine, "build", build):
            self.start().quit()
            self.start().quit()

        self.assertEqual(builds, ["touch"])


if __name__ == "__main__":
    unittest.main()
