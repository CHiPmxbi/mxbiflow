import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

from pydantic import ValidationError

from mxbiflow import __main__ as cli
from mxbiflow.models.experiment import ExperimentConfig, experiment_config_schema
from mxbiflow.models.reward import RewardEnum


class ExperimentConfigTests(unittest.TestCase):
    def test_parses_the_cogmote_config(self) -> None:
        config = ExperimentConfig.model_validate(
            {
                "experiment": "chip-std-task",
                "protocol": {"id": "p1", "name": "Habituation"},
                "repository": {"id": "r1"},
                "animals": [
                    {
                        "id": "a1",
                        "name": "Alice",
                        "rfid_tags": ["0001"],
                        "stage": "habituation",
                        "level": 2,
                    },
                    {"id": "b2", "stage": "habituation"},
                ],
                "parameters": {"reward_type": "m_juice", "fullscreen": False},
            }
        )

        self.assertEqual(config.animals[0].rfid_tags, ("0001",))
        self.assertEqual(config.animals[1].level, 0)
        self.assertEqual(config.parameters.reward_type, RewardEnum.M_JUICE)
        self.assertFalse(config.parameters.fullscreen)
        self.assertTrue(config.parameters.hide_cursor)

    def test_rejects_invalid_configs(self) -> None:
        refs = {"protocol": {"id": "p1"}, "repository": {"id": "r1"}}
        for data in [
            {"animals": [{"id": "a1", "stage": "s"}]},
            {**refs, "protocol": {"id": ""}, "animals": [{"id": "a1", "stage": "s"}]},
            {**refs, "animals": []},
            {**refs, "animals": [{"id": "a1", "stage": ""}]},
            {**refs, "animals": [{"id": "a1", "stage": "s", "level": -1}]},
            {
                **refs,
                "animals": [{"id": "a1", "stage": "s"}, {"id": "a1", "stage": "t"}],
            },
            {
                **refs,
                "animals": [{"id": "a1", "stage": "s"}],
                "parameters": {"reward_type": "x"},
            },
        ]:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                ExperimentConfig.model_validate(data)

    def test_schema_is_self_contained(self) -> None:
        schema = experiment_config_schema()

        self.assertEqual(
            schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertNotIn("$ref", json.dumps(schema))
        self.assertNotIn("$defs", schema)
        animal = schema["properties"]["animals"]["items"]
        self.assertTrue(animal["properties"]["name"]["readOnly"])
        self.assertTrue(animal["properties"]["rfid_tags"]["readOnly"])
        self.assertEqual(animal["required"], ["id", "stage"])
        reward = schema["properties"]["parameters"]["properties"]["reward_type"]
        self.assertEqual(reward["enum"], [member.value for member in RewardEnum])
        self.assertEqual(reward["default"], "agum_one_fifth")
        self.assertEqual(schema["required"], ["protocol", "repository", "animals"])
        self.assertEqual(schema["properties"]["protocol"]["x-cogmatrix"], "protocol")
        self.assertEqual(
            schema["properties"]["repository"]["x-cogmatrix"], "repository"
        )
        self.assertEqual(animal["properties"]["id"]["x-cogmatrix"], "animal")

    def test_cli_output_is_only_the_schema(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "mxbiflow", "schema"],
            capture_output=True,
            check=True,
            text=True,
        )

        self.assertEqual(json.loads(result.stdout), experiment_config_schema())

    def test_cli_prints_the_schema(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            cli.main(["schema"])

        self.assertEqual(json.loads(output.getvalue()), experiment_config_schema())


if __name__ == "__main__":
    unittest.main()
