import ast
import json
import runpy
import tempfile
import unittest
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import Field

from mxbiflow.__main__ import main
from mxbiflow.statemachine import load_experiment
from mxbiflow.statemachine.eject import eject, python_source
from mxbiflow.statemachine.machine import (
    EXIT,
    Background,
    Cancel,
    Clear,
    Count,
    Counter,
    Cross,
    Done,
    Group,
    Hide,
    Host,
    Image,
    Machine,
    On,
    Outcome,
    Play,
    Reached,
    Reset,
    Rise,
    ScreenTouch,
    SetHigh,
    SetLow,
    Show,
    Size,
    Start,
    State,
    StateParam,
    StimulusParam,
    Stop,
    Text,
    Time,
    Timeout,
    Timer,
    Tones,
    Touch,
    TrialParams,
    Wav,
)
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.models import Stage as StageData
from mxbiflow.statemachine.scene import MachineTrial
from mxbiflow.statemachine.stage import Stage

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = FIXTURES / "two_pictures.experiment.json"


class Odd(TrialParams):
    """Parameters whose names are not Python's."""

    wait_ms: Time = Field(1500, alias="wait ms")
    licks: Count = Field(2, alias="2 licks")
    stage: float = 0.25
    after: StateParam[str] = "give"
    hz: float = 4000
    which: StimulusParam[str] = "show"
    sound: StimulusParam[str] = "tone"


def everything() -> Machine:
    """A stage that uses each thing the format has, with names that are not Python's."""
    p = Odd.refs()
    return Machine(
        params=Odd,
        inputs=["lick left"],
        outputs=["reward", "laser"],
        screen=(800, 600),
        stimuli=[
            Background(name="grey", color="#808080"),
            Cross(
                name="show",
                x=p.stage,
                y=0.5,
                width=40,
                height=40,
                size=Size.px,
                color="#ffffff",
            ),
            Text(
                name='say "go"',
                text='it\'s "go"\n',
                x=0.5,
                y=0.1,
                width=0.5,
                height=0.1,
                color="#000000",
            ),
            Image(name="frame", path=None, x=0.5, y=0.5, width=0.2, height=0.2),
            Tones(name="tone", tones=[(p.hz, 100), (0, p.wait_ms)], duration_ms=600),
            Tones(name="long", tones=[(500, 50.5)], duration_ms=p.wait_ms),
            Wav(name="silence", path=None, duration_ms=250),
        ],
        timers=[Timer(name="limit", time_ms=p.wait_ms)],
        counters=[Counter(name="licked", event=Rise("lick left"), limit=p.licks)],
        groups=[
            Group(name="all", on_exit=[Cancel("laser")]),
            Group(name="trial", hold=["laser"], parent="all"),
        ],
        states=[
            State(
                name="give",
                timeout_ms=100,
                hold=["reward"],
                group="all",
                outcome=Outcome.correct,
            ),
            State(
                name="wait",
                timeout_ms=p.wait_ms,
                group="trial",
                on_entry=[
                    Show("show"),
                    Hide("show"),
                    Show(p.which),
                    Hide(p.which),
                    Play(p.sound),
                    Stop(p.sound),
                    Clear(),
                    Play("tone"),
                    Start("limit"),
                    Stop("limit"),
                    SetHigh(output="reward", after_ms=p.wait_ms),
                    SetLow(output="reward", after_ms=3.5),
                    Stop("tone"),
                    Reset("licked"),
                ],
            ),
        ],
        start="wait",
        transitions=[
            On(source="give", event=Timeout(), target=EXIT),
            On(source="wait", event=Touch("show"), target=p.after),
            On(source="wait", event=Done("tone"), target="give"),
            On(source="wait", event=Host("go"), target="give"),
            On(
                source="wait",
                event=ScreenTouch(),
                actions=[SetLow(output="laser"), Cancel("reward")],
            ),
            On(source="trial", event=Reached("licked"), target="give"),
            On(source="all", event=Done("limit"), target=EXIT),
        ],
    )


def plain(stage: StageData) -> dict[str, Any]:
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


def rebuilt(experiment: Experiment, directory: Path) -> tuple[list[StageData], str]:
    """The stages built by the Python written for ``experiment``, and that Python."""
    target = eject(experiment, directory, "a test")
    module = runpy.run_path(str(target))
    stages: list[type[MachineTrial[Any]]] = module["scenes"]
    assert all(issubclass(stage.bound_stage(), Stage) for stage in stages)
    machines = [value for value in module.values() if isinstance(value, Machine)]
    built = [
        machine.build(stage.name())
        for stage, machine in zip(stages, machines, strict=True)
    ]
    return built, target.read_text()


class EjectTests(unittest.TestCase):
    def assert_round_trip(self, experiment: Experiment) -> str:
        with tempfile.TemporaryDirectory() as directory:
            stages, source = rebuilt(experiment, Path(directory))
        self.assertEqual(
            [plain(stage) for stage in stages],
            [plain(stage) for stage in experiment.stages],
        )
        return source

    def test_the_example_comes_back_the_same(self) -> None:
        self.assert_round_trip(load_experiment(EXAMPLE))

    def test_everything_the_format_has_comes_back_the_same(self) -> None:
        stage = everything().build("class")
        self.assert_round_trip(Experiment(stages=[stage]))

    def test_the_machines_of_the_conformance_cases_come_back_the_same(self) -> None:
        cases = json.loads((FIXTURES / "conformance" / "cases.json").read_text())
        for case in cases:
            with self.subTest(case["name"]):
                self.assert_round_trip(Experiment.model_validate(case["experiment"]))

    def test_every_name_is_an_enum_member(self) -> None:
        source = self.assert_round_trip(load_experiment(EXAMPLE))

        self.assertIn("class States(StrEnum):", source)
        self.assertIn("    WAIT = auto()", source)
        # A name that is not what auto() gives keeps its spelling.
        self.assertIn('    A = "A"', source)
        self.assertIn("    on_left: StateParam[States] = States.REWARD", source)
        self.assertIn(
            "On(source=States.CHOICE, event=Rise(Inputs.LICK_LEFT), target=p.on_left)",
            source,
        )
        # No name is looked up by a string: the only ones left are colours.
        body = source[source.index("MACHINE = Machine(") :]
        strings = [
            node.value
            for node in ast.walk(ast.parse(body))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        self.assertTrue(all(s.startswith("#") or s.endswith(".svg") for s in strings))

    def test_stages_get_their_own_enums_and_classes(self) -> None:
        stage = everything().build("class")
        other = stage.model_copy(update={"name": "class_"})
        source = self.assert_round_trip(Experiment(stages=[stage, other]))

        self.assertIn("class ClassStates(StrEnum):", source)
        self.assertIn("class Class2States(StrEnum):", source)
        self.assertIn('wait_ms: Time = Field(1500, alias="wait ms")', source)
        self.assertIn("class ClassTrial(MachineTrial[ClassParams]):", source)
        self.assertIn("class Class(Stage[ClassParams]):", source)
        self.assertIn("    trial = Class2Trial", source)
        self.assertIn("scenes = [Class.scene(), Class2.scene()]", source)

    def test_a_written_stage_runs_its_trials_with_the_defaults(self) -> None:
        source = self.assert_round_trip(load_experiment(EXAMPLE))

        self.assertIn("class DiscriminateTrial(MachineTrial[Params]):", source)
        self.assertIn("class Discriminate(Stage[Params]):", source)
        self.assertIn("    trial = DiscriminateTrial", source)
        self.assertIn("        return Stages.DISCRIMINATE", source)
        self.assertIn(
            "    def next_trial(self) -> Params:\n        return Params()", source
        )

    def test_pictures_become_files(self) -> None:
        source, files = python_source(load_experiment(EXAMPLE), "x")
        self.assertEqual(len(files), 2)
        self.assertTrue(all(name.endswith(".svg") for name in files))
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
        self.assertIn("scenes = [Discriminate.scene()]", written)


if __name__ == "__main__":
    unittest.main()
