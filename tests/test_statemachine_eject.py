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
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.models import Stage as StageData
from mxbiflow.statemachine.stage import (
    EXIT,
    Background,
    Choice,
    Clear,
    Count,
    Counter,
    CountRule,
    Cross,
    Done,
    Factor,
    Generator,
    Group,
    Hide,
    Host,
    Image,
    Level,
    On,
    Order,
    Outcome,
    Play,
    Reached,
    Reset,
    Rise,
    Row,
    Show,
    Size,
    Stage,
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
    Uniform,
    Wav,
)

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


def everything() -> Stage:
    """A stage that uses each thing the format has, with names that are not Python's."""
    p = Odd.refs()
    return Stage(
        name="class",
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
        generators=[
            Generator(name="pulses", output="laser", width_ms=5, period_ms=20, count=0),
            Generator(name="one", output="laser", width_ms=p.wait_ms, delay_ms=3),
        ],
        counters=[Counter(name="licked", event=Rise("lick left"), limit=p.licks)],
        groups=[Group(name="all"), Group(name="trial", hold=["laser"], parent="all")],
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
                    Stop("pulses"),
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
            On(source="trial", event=Reached("licked"), target="give"),
            On(source="all", event=Done("limit"), target=EXIT),
        ],
        levels=[
            Level(name="easy"),
            Level(
                name="hard",
                values={
                    p.wait_ms: Uniform(low=500, high=900.5),
                    p.licks: 3,
                    p.hz: Choice(4000, 8000),
                    p.sound: Choice("tone"),
                },
                factors=[
                    Factor(
                        name="side",
                        rows=[
                            Row(name="left", values={p.stage: 0.25, p.after: "give"}),
                            Row(name="right", values={p.stage: 0.75}, weight=2.5),
                        ],
                        order=Order.cycle,
                    ),
                    Factor(
                        name="which",
                        rows=[
                            Row(name="cue", values={p.which: "show"}),
                            Row(name="frame", values={p.which: "frame"}),
                        ],
                    ),
                ],
            ),
        ],
        rule=CountRule(5),
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
    stages = [value for value in module.values() if isinstance(value, Stage)]
    return [stage.build()[0] for stage in stages], target.read_text()


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
        stage, _ = everything().build()
        self.assert_round_trip(Experiment(stages=[stage], animals=[]))

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
        self.assertIn('    A_LEFT = "A left"', source)
        self.assertIn("    on_left: StateParam[States] = States.REWARD", source)
        self.assertIn(
            "On(source=States.CHOICE, event=Rise(Inputs.LICK_LEFT), target=p.on_left)",
            source,
        )
        self.assertIn("Choice(6000, 9500, 12000)", source)
        # No name is looked up by a string: the only ones left are colours.
        body = source[source.index("discriminate = Stage(") :]
        strings = [
            node.value
            for node in ast.walk(ast.parse(body))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        self.assertTrue(all(s.startswith("#") or s.endswith(".svg") for s in strings))

    def test_stages_get_their_own_enums(self) -> None:
        stage, _ = everything().build()
        other = stage.model_copy(update={"name": "class_"})
        source = self.assert_round_trip(Experiment(stages=[stage, other], animals=[]))

        self.assertIn("class ClassStates(StrEnum):", source)
        self.assertIn("class Class2States(StrEnum):", source)
        self.assertIn('wait_ms: Time = Field(1500, alias="wait ms")', source)

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
        self.assertIn("scenes = stage_scenes(discriminate)", written)


if __name__ == "__main__":
    unittest.main()
