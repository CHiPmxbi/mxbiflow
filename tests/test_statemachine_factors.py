"""Factors, choices, stimulus parameters and tones set per trial."""

import unittest
from enum import StrEnum, auto

from mxbiflow.statemachine import machine_scenes
from mxbiflow.statemachine.host import Progress, draw_trial, settle
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.runner import Trial
from mxbiflow.statemachine.stage import (
    EXIT,
    Choice,
    CountRule,
    Done,
    Factor,
    Level,
    On,
    Order,
    Outcome,
    Play,
    Rect,
    Row,
    Show,
    Stage,
    State,
    StimulusParam,
    Time,
    Tones,
    TrialParams,
    Uniform,
    stage_scenes,
)


class S(StrEnum):
    CUE = auto()


class Stim(StrEnum):
    A = auto()
    B = auto()
    LOW = auto()
    HIGH = auto()


class F(StrEnum):
    PICTURE = auto()
    SOUND = auto()


class Params(TrialParams):
    picture: StimulusParam[Stim] = Stim.A
    sound: StimulusParam[Stim] = Stim.LOW
    hz: float = 1000
    tone_ms: Time = 100


p = Params.refs()
PICTURES = Factor(
    name=F.PICTURE,
    rows=[
        Row(name=Stim.A, values={p.picture: Stim.A}),
        Row(name=Stim.B, values={p.picture: Stim.B}),
    ],
)
SOUNDS = [
    Row(name=Stim.LOW, values={p.sound: Stim.LOW}),
    Row(name=Stim.HIGH, values={p.sound: Stim.HIGH}),
]


def pictures(*levels: Level, rule: CountRule | None = None) -> Stage:
    """Show the picture and play the sound a trial draws."""
    return Stage(
        name="pictures",
        params=Params,
        screen=(200, 100),
        stimuli=[
            *(
                Rect(name=name, x=0.5, y=0.5, width=0.2, height=0.2, color="#ffffff")
                for name in (Stim.A, Stim.B)
            ),
            Tones(name=Stim.LOW, tones=[(p.hz, p.tone_ms)], duration_ms=p.tone_ms),
            Tones(name=Stim.HIGH, tones=[(8000, 50)], duration_ms=50),
        ],
        states=[
            State(
                name=S.CUE,
                on_entry=[Show(p.picture), Play(p.sound)],
                outcome=Outcome.correct,
            )
        ],
        transitions=[On(source=S.CUE, event=Done(p.sound), target=EXIT)],
        levels=levels,
        rule=rule,
    )


def experiment_of(stage: Stage) -> Experiment:
    return Experiment(stages=[stage.build()[0]], animals=[])


def numbers(*values: float):
    left = iter(values)
    return lambda: next(left)


class DrawTests(unittest.TestCase):
    def test_each_factor_draws_its_own_row_after_the_level_values(self) -> None:
        level = Level(
            name=1,
            values={
                p.hz: Choice(500, 1000, 2000),
                p.tone_ms: Uniform(low=100, high=200),
            },
            factors=[
                PICTURES,
                Factor(
                    name=F.SOUND,
                    rows=[
                        Row(name=Stim.LOW, values={p.sound: Stim.LOW}, weight=3),
                        SOUNDS[1],
                    ],
                ),
            ],
        )

        draw = draw_trial(
            experiment_of(pictures(level)),
            {},
            Progress(0, 0),
            numbers(0.99, 0.505, 0.6, 0.8),
        )

        # The choice, the range (rounded: a time), then one number per factor.
        self.assertEqual(draw.values["hz"], 2000)
        self.assertEqual(draw.values["tone_ms"], 151)
        self.assertEqual(draw.factors, {"picture": "b", "sound": "high"})
        self.assertEqual(draw.values["picture"], "b")
        self.assertEqual(draw.cursors, {})

    def test_factors_in_turn_keep_a_cursor_each_and_use_no_random_number(self) -> None:
        level = Level(
            name=1,
            factors=[
                Factor(name=F.PICTURE, rows=PICTURES.rows, order=Order.cycle),
                Factor(
                    name=F.SOUND, rows=[*SOUNDS, Row(name="again")], order=Order.cycle
                ),
            ],
        )
        experiment = experiment_of(pictures(level))

        progress = Progress(0, 0)
        drawn: list[dict[str, str]] = []
        for _ in range(3):
            draw = draw_trial(experiment, {}, progress, numbers())
            drawn.append(draw.factors)
            progress = Progress(0, 0, cursors=draw.cursors)

        self.assertEqual(
            drawn,
            [
                {"picture": "a", "sound": "low"},
                {"picture": "b", "sound": "high"},
                {"picture": "a", "sound": "again"},
            ],
        )
        self.assertEqual(progress.cursors, {"picture": 3, "sound": 3})

    def test_a_random_number_of_nearly_one_draws_the_last_row_with_weight(self) -> None:
        rows = [
            PICTURES.rows[0],
            Row(name=Stim.B, values={p.picture: Stim.B}, weight=0),
        ]
        level = Level(name=1, factors=[Factor(name=F.PICTURE, rows=rows)])

        draw = draw_trial(
            experiment_of(pictures(level)), {}, Progress(0, 0), numbers(1.0)
        )

        self.assertEqual(draw.factors, {"picture": "a"})

    def test_a_missing_stage_or_level_raises(self) -> None:
        experiment = experiment_of(pictures())
        with self.assertRaisesRegex(ValueError, "no stage 1"):
            draw_trial(experiment, {}, Progress(1, 0))
        with self.assertRaisesRegex(ValueError, "no level 3"):
            draw_trial(experiment, {}, Progress(0, 3))

    def test_a_new_level_starts_its_factors_from_the_first_row(self) -> None:
        stage = pictures(Level(name=1), Level(name=2), rule=CountRule(1))

        progress, action = settle(
            experiment_of(stage), Progress(0, 0, cursors={"picture": 5}), "correct"
        )

        self.assertEqual(action, "level up")
        self.assertEqual(progress.cursors, {})


class TrialTests(unittest.TestCase):
    def trial(self, **values: float | str) -> Trial:
        machine = pictures().build()[0].machine
        return Trial(machine, values=dict(values))

    def test_the_stimuli_a_trial_names_are_shown_and_played(self) -> None:
        trial = self.trial(picture="b", sound="high", hz=1000, tone_ms=100)

        self.assertEqual(trial.shown, ["b"])
        self.assertEqual(trial.sounds, {"high": 50})

    def test_a_tones_length_is_the_trials(self) -> None:
        trial = self.trial(picture="a", sound="low", hz=500, tone_ms=240)

        self.assertEqual(trial.sounds, {"low": 240})

    def test_an_event_of_a_stimulus_parameter_is_that_of_each_it_can_name(self) -> None:
        level = Level(name=1, values={p.sound: Choice(Stim.LOW, Stim.HIGH)})
        machine = pictures(level).build()[0].machine

        self.assertEqual(
            [t.event for t in machine.states[0].transitions], ["low.done", "high.done"]
        )

    def test_a_stimulus_that_is_not_there_is_said_in_the_log(self) -> None:
        trial = self.trial(picture="low", sound="nothing", hz=500, tone_ms=0)

        self.assertEqual(trial.shown, [])
        self.assertEqual(trial.sounds, {})
        texts = [entry.text for entry in trial.log]
        self.assertIn('no stimulus "low" ($picture)', texts)
        self.assertIn('no stimulus "nothing" ($sound)', texts)

    def test_a_tone_drawn_with_no_length_is_not_played(self) -> None:
        trial = self.trial(picture="a", sound="low", hz=500, tone_ms=0)

        self.assertEqual(trial.sounds, {})
        self.assertIn(
            "low: a tone's duration is not positive", [e.text for e in trial.log]
        )


class ValidationTests(unittest.TestCase):
    def assert_refused(self, level: Level, message: str) -> None:
        with self.assertRaisesRegex(ValueError, message):
            pictures(level).build()

    def test_a_parameter_set_by_the_level_and_a_factor_is_refused(self) -> None:
        level = Level(name=1, values={p.picture: Stim.A}, factors=[PICTURES])
        self.assert_refused(level, "picture is set twice, by 1 and by picture")

    def test_a_parameter_set_by_two_factors_is_refused(self) -> None:
        level = Level(
            name=1, factors=[PICTURES, Factor(name="second", rows=PICTURES.rows)]
        )
        self.assert_refused(level, "picture is set twice, by picture and by second")

    def test_a_factor_without_rows_or_weights_is_refused(self) -> None:
        never = Factor(
            name="never", rows=[Row(name=Stim.A, values={p.picture: Stim.A}, weight=0)]
        )
        level = Level(name=1, factors=[Factor(name="empty", rows=[]), never])
        self.assert_refused(level, "empty: the factor has no rows.*weight is 0")

    def test_a_factor_named_twice_is_refused(self) -> None:
        level = Level(
            name=1,
            factors=[
                PICTURES,
                Factor(name=F.PICTURE, rows=[Row(name="x", values={p.hz: 1})]),
            ],
        )
        self.assert_refused(level, "the factor's name is used twice")

    def test_a_stimulus_parameter_must_name_a_stimulus_of_its_use(self) -> None:
        level = Level(
            name=1,
            values={
                p.picture: Stim.LOW,
                p.sound: Choice(Stim.A, "nothing"),
                p.hz: Stim.A,
            },
        )
        self.assert_refused(
            level,
            'picture: "low" is not a stimulus on the screen.*'
            'sound: "a" is not a sound.*sound: "nothing" is not a sound.*'
            "hz needs a number",
        )

    def test_a_stimulus_parameter_needs_a_name_not_a_number(self) -> None:
        self.assert_refused(
            Level(name=1, values={p.picture: 1}), "picture needs a stimulus"
        )

    def test_a_stimulus_parameter_both_shown_and_played_is_refused(self) -> None:
        class Both(TrialParams):
            either: StimulusParam[Stim] = Stim.A

        either = Both.refs().either
        stage = Stage(
            name="both",
            params=Both,
            stimuli=[
                Rect(name=Stim.A, x=0.5, y=0.5, width=0.2, height=0.2, color="#ffffff")
            ],
            states=[State(name=S.CUE, on_entry=[Show(either), Play(either)])],
        )
        with self.assertRaisesRegex(ValueError, "either is both shown and played"):
            stage.build()

    def test_an_experiment_file_with_such_a_level_does_not_become_scenes(self) -> None:
        stage = pictures(Level(name=1, values={p.picture: Stim.A}))
        broken = stage.build()[0].model_dump(mode="json", by_alias=True)
        broken["levels"][0]["factors"] = [{"name": "f", "order": "random", "rows": []}]
        experiment = Experiment.model_validate({"stages": [broken], "animals": []})

        with self.assertRaisesRegex(ValueError, "the factor has no rows"):
            machine_scenes(experiment)
        self.assertIn("pictures", stage_scenes(stage))


if __name__ == "__main__":
    unittest.main()
