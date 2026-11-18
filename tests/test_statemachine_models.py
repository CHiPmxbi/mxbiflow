import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from mxbiflow.statemachine import load_experiment
from mxbiflow.statemachine.models import RateProgression, Value1

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "tests" / "fixtures" / "two_pictures.experiment.json"


class GeneratedModelsTests(unittest.TestCase):
    def test_models_match_the_schema(self) -> None:
        # Settings come from [tool.datamodel-codegen] in pyproject.toml.
        result = subprocess.run(
            [sys.executable, "-m", "datamodel_code_generator", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            "models.py is out of date with experiment.schema.json; "
            f"run `uv run datamodel-codegen`\n{result.stdout}{result.stderr}",
        )


class LoadExperimentTests(unittest.TestCase):
    def test_loads_the_cogforge_example(self) -> None:
        experiment = load_experiment(EXAMPLE)

        stage = experiment.stages[0]
        self.assertEqual(stage.name, "discriminate")
        self.assertEqual([level.name for level in stage.levels], ["1", "2"])
        self.assertEqual(stage.levels[0].values["choice_ms"], 10000)
        self.assertEqual(
            stage.levels[1].values["choice_ms"], Value1(uniform=(3000, 5000))
        )
        self.assertEqual(
            stage.progression,
            RateProgression(rule="rate", min_trials=10, up=0.8, down=0.3),
        )
        self.assertEqual([animal.name for animal in experiment.animals], ["mock_001"])

    def test_rejects_an_unknown_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text('{"stages": [], "animals": [], "extra": 1}')

            with self.assertRaises(ValidationError):
                load_experiment(path)
