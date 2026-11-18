"""Factors, choices, stimulus parameters and tones set per trial."""

import unittest

from mxbiflow.statemachine.builder import (
    EXIT,
    StageBuilder,
    play,
    show,
    stage_scenes,
)
from mxbiflow.statemachine.host import Progress, draw_trial, settle
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.runner import Trial


def pictures() -> StageBuilder:
    """Show the picture and play the sound a trial draws."""
    stage = StageBuilder("pictures", outputs=["reward"], screen=(200, 100))
    picture = stage.add_stimulus_parameter("picture", "a")
    sound = stage.add_stimulus_parameter("sound", "low")
    hz = stage.add_number("hz", 1000)
    tone_ms = stage.add_time("tone_ms", 100)
    for name in ("a", "b"):
        stage.add_rect(name, x=0.5, y=0.5, width=0.2, height=0.2, color="#ffffff")
    stage.add_tones("low", [(hz, tone_ms)], tone_ms)
    stage.add_tones("high", [(8000, 50)], 50)
    stage.add_state("cue", on_entry=[show(picture), play(sound)])
    stage.add_transition("cue", "low.done", EXIT)
    stage.add_transition("cue", "high.done", EXIT)
    return stage


def experiment_of(stage: StageBuilder) -> Experiment:
    return Experiment(stages=[stage.build()[0]], animals=[])


def numbers(*values: float):
    left = iter(values)
    return lambda: next(left)


class DrawTests(unittest.TestCase):
    def test_each_factor_draws_its_own_row_after_the_level_values(self) -> None:
        stage = pictures()
        level = stage.add_level("1", {"hz": [500, 1000, 2000], "tone_ms": (100, 200)})
        stage.add_factor(
            level, "picture", {"a": {"picture": "a"}, "b": {"picture": "b"}}
        )
        stage.add_factor(
            level,
            "sound",
            {"low": {"sound": "low"}, "high": {"sound": "high"}},
            weights={"low": 3},
        )

        draw = draw_trial(
            experiment_of(stage), {}, Progress(0, 0), numbers(0.99, 0.505, 0.6, 0.8)
        )

        # The choice, the range (rounded: a time), then one number per factor.
        self.assertEqual(draw.values["hz"], 2000)
        self.assertEqual(draw.values["tone_ms"], 151)
        self.assertEqual(draw.factors, {"picture": "b", "sound": "high"})
        self.assertEqual(draw.values["picture"], "b")
        self.assertEqual(draw.cursors, {})

    def test_factors_in_turn_keep_a_cursor_each_and_use_no_random_number(self) -> None:
        stage = pictures()
        level = stage.add_level("1")
        stage.add_factor(
            level,
            "picture",
            {"a": {"picture": "a"}, "b": {"picture": "b"}},
            order="cycle",
        )
        stage.add_factor(
            level,
            "sound",
            {"low": {"sound": "low"}, "high": {"sound": "high"}, "again": {}},
            order="cycle",
        )
        experiment = experiment_of(stage)

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
        stage = pictures()
        level = stage.add_level("1")
        stage.add_factor(
            level,
            "picture",
            {"a": {"picture": "a"}, "b": {"picture": "b"}},
            weights={"b": 0},
        )

        draw = draw_trial(experiment_of(stage), {}, Progress(0, 0), numbers(1.0))

        self.assertEqual(draw.factors, {"picture": "a"})

    def test_a_missing_stage_or_level_raises(self) -> None:
        experiment = experiment_of(pictures())
        with self.assertRaisesRegex(ValueError, "no stage 1"):
            draw_trial(experiment, {}, Progress(1, 0))
        with self.assertRaisesRegex(ValueError, "no level 3"):
            draw_trial(experiment, {}, Progress(0, 3))

    def test_a_new_level_starts_its_factors_from_the_first_row(self) -> None:
        stage = pictures()
        stage.add_level("1")
        stage.add_level("2")
        stage.set_outcome("cue", "correct")
        stage.set_count_rule(1)

        progress, action = settle(
            experiment_of(stage), Progress(0, 0, cursors={"picture": 5}), "correct"
        )

        self.assertEqual(action, "level up")
        self.assertEqual(progress.cursors, {})


class TrialTests(unittest.TestCase):
    def test_the_stimuli_a_trial_names_are_shown_and_played(self) -> None:
        machine = pictures().build()[0].machine
        values = {"picture": "b", "sound": "high", "hz": 1000, "tone_ms": 100}

        trial = Trial(machine, values=dict(values))

        self.assertEqual(trial.shown, ["b"])
        self.assertEqual(trial.sounds, {"high": 50})

    def test_a_tones_length_is_the_trials(self) -> None:
        machine = pictures().build()[0].machine
        values = {"picture": "a", "sound": "low", "hz": 500, "tone_ms": 240}

        trial = Trial(machine, values=dict(values))

        self.assertEqual(trial.sounds, {"low": 240})

    def test_a_stimulus_that_is_not_there_is_said_in_the_log(self) -> None:
        machine = pictures().build()[0].machine
        values = {"picture": "low", "sound": "nothing", "hz": 500, "tone_ms": 0}

        trial = Trial(machine, values=dict(values))

        self.assertEqual(trial.shown, [])
        self.assertEqual(trial.sounds, {})
        texts = [entry.text for entry in trial.log]
        self.assertIn('no stimulus "low" ($picture)', texts)
        self.assertIn('no stimulus "nothing" ($sound)', texts)

    def test_a_tone_drawn_with_no_length_is_not_played(self) -> None:
        machine = pictures().build()[0].machine
        values = {"picture": "a", "sound": "low", "hz": 500, "tone_ms": 0}

        trial = Trial(machine, values=dict(values))

        self.assertEqual(trial.sounds, {})
        self.assertIn(
            "low: a tone's duration is not positive", [e.text for e in trial.log]
        )


class ValidationTests(unittest.TestCase):
    def assert_refused(self, stage: StageBuilder, message: str) -> None:
        with self.assertRaisesRegex(ValueError, message):
            stage.build()

    def test_a_parameter_set_by_the_level_and_a_factor_is_refused(self) -> None:
        stage = pictures()
        level = stage.add_level("1", {"picture": "a"})
        stage.add_factor(level, "which", {"b": {"picture": "b"}})
        self.assert_refused(stage, "picture is set twice, by 1 and by which")

    def test_a_parameter_set_by_two_factors_is_refused(self) -> None:
        stage = pictures()
        level = stage.add_level("1")
        stage.add_factor(level, "first", {"a": {"picture": "a"}})
        stage.add_factor(level, "second", {"b": {"picture": "b"}})
        self.assert_refused(stage, "picture is set twice, by first and by second")

    def test_a_factor_without_rows_or_weights_is_refused(self) -> None:
        stage = pictures()
        level = stage.add_level("1")
        stage.add_factor(level, "empty", {})
        stage.add_factor(level, "never", {"a": {"picture": "a"}}, weights={"a": 0})
        self.assert_refused(stage, "empty: the factor has no rows.*weight is 0")

    def test_a_factor_named_twice_is_refused(self) -> None:
        stage = pictures()
        level = stage.add_level("1")
        stage.add_factor(level, "same", {"a": {"picture": "a"}})
        stage.add_factor(level, "same", {"x": {"hz": 1}})
        self.assert_refused(stage, "the factor's name is used twice")

    def test_a_stimulus_parameter_must_name_a_stimulus_of_its_use(self) -> None:
        stage = pictures()
        stage.add_level("1", {"picture": "low", "sound": ["a", "nothing"], "hz": "a"})
        self.assert_refused(
            stage,
            'picture: "low" is not a stimulus on the screen.*'
            'sound: "a" is not a sound.*sound: "nothing" is not a sound.*'
            "hz needs a number",
        )

    def test_a_stimulus_parameter_needs_a_name_not_a_number(self) -> None:
        stage = pictures()
        stage.add_level("1", {"picture": 1})
        self.assert_refused(stage, "picture needs a stimulus")

    def test_a_stimulus_parameter_both_shown_and_played_is_refused(self) -> None:
        stage = StageBuilder("both")
        either = stage.add_stimulus_parameter("either", "a")
        stage.add_rect("a", x=0.5, y=0.5, width=0.2, height=0.2, color="#ffffff")
        stage.add_state("cue", on_entry=[show(either), play(either)])
        self.assert_refused(stage, "either is both shown and played")

    def test_an_experiment_file_with_such_a_level_does_not_become_scenes(self) -> None:
        stage = pictures()
        stage.add_level("1", {"picture": "a"})
        built = stage.build()[0]
        factor = {"name": "f", "order": "random", "rows": []}
        broken = built.model_dump(mode="json", by_alias=True)
        broken["levels"][0]["factors"] = [factor]
        experiment = Experiment.model_validate({"stages": [broken], "animals": []})

        from mxbiflow.statemachine import machine_scenes

        with self.assertRaisesRegex(ValueError, "the factor has no rows"):
            machine_scenes(experiment)
        self.assertIn("pictures", stage_scenes(stage))


if __name__ == "__main__":
    unittest.main()
