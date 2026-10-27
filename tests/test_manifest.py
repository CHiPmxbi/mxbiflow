import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import Mock, patch

from pydantic import BaseModel, Field, ValidationError

from mxbiflow import run
from mxbiflow.core.path import set_base_path
from mxbiflow.models.experiment import inlined_json_schema
from mxbiflow.models.stage_config import StageConfig, for_animal, merge_overrides
from mxbiflow.scene import Scene, SceneManager

TEMPLATE: dict[str, Any] = {
    "default": {
        "reward_ms": 100,
        "levels": {
            "2": {"target_size": 0.3},
            "1": {"target_size": 0.4},
        },
    },
    "Apollo": {"levels": {"2": {"target_size": 0.35}}},
}


class Level(BaseModel):
    target_size: float = Field(gt=0, le=1, title="Target size")


class TouchConfig(StageConfig[Level]):
    reward_ms: int = Field(gt=0, title="Reward", json_schema_extra={"unit": "ms"})


class Touch(Scene):
    title = "Touchscreen training"
    description = "Touch a single target."
    config_model = TouchConfig

    def start(self) -> None: ...
    def quit(self) -> None: ...
    def handle_event(self, event: object) -> None: ...
    def update(self, dt_s: float) -> None: ...
    def draw(self, screen: object) -> None: ...


class Plain(Touch):
    title = ""
    description = ""
    config_model = None
    config_template = None
    level_table: ClassVar[dict[str, list[int]]] = {"default": [1, 2, 3]}


class StageConfigTests(unittest.TestCase):
    def test_overrides_merge_over_the_default(self) -> None:
        config = for_animal(TouchConfig, TEMPLATE, "Apollo")
        self.assertEqual(config.reward_ms, 100)
        self.assertEqual(config.levels[1].target_size, 0.4)
        self.assertEqual(config.levels[2].target_size, 0.35)
        self.assertEqual(
            for_animal(TouchConfig, TEMPLATE, "Bob").levels[2].target_size, 0.3
        )

    def test_merged_overrides_are_validated(self) -> None:
        document = {**TEMPLATE, "Bob": {"levels": {"1": {"target_size": 2}}}}
        with self.assertRaises(ValidationError):
            for_animal(TouchConfig, document, "Bob")
        with self.assertRaisesRegex(ValueError, "default"):
            for_animal(TouchConfig, {"Bob": {}}, "Bob")

    def test_merge_keeps_the_default_untouched(self) -> None:
        default = {"a": {"b": 1, "c": 2}}
        self.assertEqual(
            merge_overrides(default, {"a": {"c": 3}}), {"a": {"b": 1, "c": 3}}
        )
        self.assertEqual(default, {"a": {"b": 1, "c": 2}})

    def test_schema_marks_the_level_table(self) -> None:
        schema = inlined_json_schema(TouchConfig)
        levels = schema["properties"]["levels"]
        self.assertTrue(levels["x-mxbi-levels"])
        self.assertEqual(levels["propertyNames"]["type"], "string")
        self.assertEqual(schema["properties"]["reward_ms"]["unit"], "ms")

    def test_config_document_prefers_the_cogmote_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Touch.config_template = Path(tmp) / "config.json"
            Touch.config_template.write_text(json.dumps(TEMPLATE))
            context = Mock()
            context.session.config.stage_configs = {}
            with patch("mxbiflow.core.context.get_mxbiflow", return_value=context):
                self.assertEqual(Touch.config_document(), TEMPLATE)
                cogmote = {"default": {**TEMPLATE["default"], "reward_ms": 5}}
                context.session.config.stage_configs = {"touch": cogmote}
                self.assertEqual(Touch.config_document(), cogmote)


class DescribeTests(unittest.TestCase):
    def test_describe_prints_the_manifest_without_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "pyproject.toml").write_text(
                '[project]\nname = "touch-task"\nversion = "1.4.0"\n'
            )
            Touch.config_template = base / "config.json"
            Touch.config_template.write_text(json.dumps(TEMPLATE))
            set_base_path(base)
            scenes = SceneManager()
            scenes.register([Touch, Plain])
            out = io.StringIO()
            with (
                patch.object(run, "init_gameloop", side_effect=AssertionError),
                patch.object(run, "run_wizard", side_effect=AssertionError),
                redirect_stdout(out),
            ):
                run.run_experiment(scenes, argv=["--describe"])

        manifest = json.loads(out.getvalue())
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(
            (manifest["name"], manifest["version"]), ("touch-task", "1.4.0")
        )
        self.assertIn("animals", manifest["config_schema"]["properties"])
        touch, plain = manifest["stages"]
        self.assertEqual(touch["name"], "touch")
        self.assertEqual(touch["title"], "Touchscreen training")
        self.assertEqual(touch["description"], "Touch a single target.")
        self.assertEqual(
            touch["levels"],
            [{"id": 1, "target_size": 0.4}, {"id": 2, "target_size": 0.3}],
        )
        self.assertTrue(touch["schema"]["properties"]["levels"]["x-mxbi-levels"])
        self.assertEqual(touch["template"], TEMPLATE)
        self.assertEqual(plain["title"], "Plain")
        self.assertEqual(plain["levels"], [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertIsNone(plain["schema"])


if __name__ == "__main__":
    unittest.main()
