import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from mxbiflow.statemachine import load_experiment
from mxbiflow.statemachine.models import Outcomes

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
        self.assertEqual(
            stage.outcomes,
            {"reward": Outcomes.correct, "error": Outcomes.incorrect},
        )
        self.assertEqual(
            [parameter.name for parameter in stage.machine.parameters][:2],
            ["on_left", "on_right"],
        )

    def test_rejects_a_file_of_the_format_with_levels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            old = load_experiment(EXAMPLE).model_dump(mode="json", by_alias=True)
            old["stages"][0]["levels"] = []
            path.write_text(json.dumps(old))

            with self.assertRaises(ValidationError):
                load_experiment(path)

    def test_rejects_an_unknown_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            path.write_text('{"stages": [], "extra": 1}')

            with self.assertRaises(ValidationError):
                load_experiment(path)
