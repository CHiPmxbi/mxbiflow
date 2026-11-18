import json
import runpy
import tempfile
import unittest
import urllib.request
from pathlib import Path
from typing import Any

from mxbiflow.__main__ import main
from mxbiflow.statemachine import load_experiment
from mxbiflow.statemachine.builder import (
    EXIT,
    StageBuilder,
    clear,
    hide,
    play,
    reset,
    show,
    start,
    stop,
)
from mxbiflow.statemachine.eject import eject, python_source
from mxbiflow.statemachine.models import Experiment, Stage

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = FIXTURES / "two_pictures.experiment.json"


def everything() -> StageBuilder:
    """A stage that uses each thing the format has, with names that are not Python's."""
    stage = StageBuilder(
        "class", inputs=["lick left"], outputs=["reward", "laser"], screen=(800, 600)
    )
    wait_ms = stage.add_time("wait ms", 1500)
    licks = stage.add_count("2 licks", 2)
    x = stage.add_number("stage", 0.25)
    after = stage.add_target("after", "give")
    stage.add_background("grey", "#808080")
    cue = stage.add_cross(
        "show", x=x, y=0.5, width=40, height=40, size="px", color="#ffffff"
    )
    stage.add_text(
        'say "go"', 'it\'s "go"\n', x=0.5, y=0.1, width=0.5, height=0.1, color="#000000"
    )
    stage.add_image("frame", None, x=0.5, y=0.5, width=0.2, height=0.2)
    tone = stage.add_tones("tone", [(4000, 100), (0, 50.5)], 600)
    stage.add_wav("silence", None, duration_ms=250)
    stage.add_timer("limit", wait_ms)
    stage.add_generator("pulses", "laser", width=5, period=20, count=0)
    stage.add_generator("one", "laser", width=wait_ms, delay=3)
    stage.add_counter("licked", "lick left.rise", licks)
    stage.add_group("all")
    stage.add_group("trial", hold=["laser"], parent="all")
    stage.add_state("give", hold=["reward"], timeout=100, group="all")
    stage.add_state(
        "wait",
        on_entry=[
            show(cue),
            hide(cue),
            clear(),
            play(tone),
            start("limit"),
            stop("pulses"),
            stop(tone),
            reset("licked"),
        ],
        timeout=wait_ms,
        group="trial",
    )
    stage.set_start("wait")
    stage.add_transition("give", "timeout", EXIT)
    stage.add_transition("wait", f"{cue}.touch", after)
    stage.add_transition("wait", f"{tone}.done", "give")
    stage.add_transition("wait", "host.go", "give")
    stage.add_transition("trial", "licked.reached", "give")
    stage.add_transition("all", "limit.done", EXIT)
    stage.set_outcome("give", "correct")
    stage.add_level("easy")
    stage.add_level(
        "hard",
        {"wait ms": (500, 900.5), "2 licks": 3},
        types={"left": {"stage": 0.25, "after": "give"}, "right": {"stage": 0.75}},
        weights={"right": 2.5},
        order="cycle",
    )
    stage.set_count_rule(5)
    return stage


def plain(stage: Stage) -> dict[str, Any]:
    """A stage as data, without what a round trip need not keep.

    cogforge's node positions are not written, and a picture or sound comes back as
    the same bytes but not as the same data URL.
    """
    data = stage.model_dump(mode="json", by_alias=True)
    data["machine"]["layout"] = {}
    for stimulus in data["machine"]["stimuli"]:
        for key in ("image", "sound"):
            if stimulus.get(key) is not None:
                with urllib.request.urlopen(stimulus[key]) as response:
                    kind = response.headers.get_content_maintype()
                    stimulus[key] = [kind, response.read().hex()]
    return data


def rebuilt(experiment: Experiment, directory: Path) -> list[Stage]:
    """The stages built by the Python written for ``experiment``."""
    module = runpy.run_path(str(eject(experiment, directory, "a test")))
    builders = [
        value()
        for value in module.values()
        if getattr(value, "__module__", None) == "<run_path>"
    ]
    return [builder.build()[0] for builder in builders]


class EjectTests(unittest.TestCase):
    def assert_round_trip(self, experiment: Experiment) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stages = rebuilt(experiment, Path(directory))
        self.assertEqual(
            [plain(stage) for stage in stages],
            [plain(stage) for stage in experiment.stages],
        )

    def test_the_example_comes_back_the_same(self) -> None:
        self.assert_round_trip(load_experiment(EXAMPLE))

    def test_everything_the_format_has_comes_back_the_same(self) -> None:
        stage, _ = everything().build()
        self.assert_round_trip(Experiment(stages=[stage], animals=[]))

    def test_the_machines_of_the_conformance_cases_come_back_the_same(self) -> None:
        cases = json.loads((FIXTURES / "conformance" / "cases.json").read_text())
        for case in cases:
            with self.subTest(case["name"]):
                self.assert_round_trip(Experiment.model_validate(case["experiment"]))

    def test_stages_of_one_name_in_python_get_their_own_functions(self) -> None:
        stage, _ = everything().build()
        other = stage.model_copy(update={"name": "class_"})
        source, _ = python_source(Experiment(stages=[stage, other], animals=[]), "x")
        self.assertIn("def class_()", source)
        self.assertIn("def class__2()", source)

    def test_pictures_become_files_and_animal_values_are_kept(self) -> None:
        experiment = load_experiment(EXAMPLE)
        experiment.animals[0].values["choice_ms"] = 4000
        source, files = python_source(experiment, "x")
        self.assertEqual(len(files), 2)
        self.assertTrue(all(name.endswith(".svg") for name in files))
        self.assertIn("animal_values={'mock_001': {'choice_ms': 4000}}", source)
        self.assertNotIn("data:image", source)

    def test_an_existing_file_is_not_written_over(self) -> None:
        experiment = load_experiment(EXAMPLE)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "stages.py").write_text("mine\n")
            with self.assertRaises(FileExistsError):
                eject(experiment, Path(directory), "x")
            self.assertEqual((Path(directory) / "stages.py").read_text(), "mine\n")

    def test_the_command_writes_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            main(["eject", str(EXAMPLE), directory])
            written = (Path(directory) / "stages.py").read_text()
        self.assertIn("two_pictures.experiment.json", written)
        self.assertIn("scenes = stage_scenes(discriminate())", written)


if __name__ == "__main__":
    unittest.main()
