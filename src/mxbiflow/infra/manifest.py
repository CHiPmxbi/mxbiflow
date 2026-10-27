"""The experiment manifest that ``run_experiment --describe`` prints (CHiPmxbi/mxbiflow#201).

It describes what cogmote needs of an installed experiment: its stages in
registration order with titles, levels, configuration schema and ``config.json``
template, the schema of the cogmote experiment configuration and of the rig
hardware configuration (#210). It is
written at install time, so describing touches no window, hardware or run.
"""

import json
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ..driver import MXBIModel
from ..models.experiment import experiment_config_schema, inlined_json_schema
from ..models.stage_config import DEFAULT_KEY
from ..scene import Scene, SceneManager
from ..scene.idle.idle import IDLE

MANIFEST_VERSION = 1


def describe(scene_manager: SceneManager, base_path: Path) -> dict[str, Any]:
    """Return the manifest of the experiment at ``base_path`` with its registered stages."""
    project = tomllib.loads((base_path / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "manifest_version": MANIFEST_VERSION,
        "name": project["project"]["name"],
        "version": project["project"]["version"],
        "mxbiflow_version": version("mxbiflow"),
        "config_schema": experiment_config_schema(),
        "hardware_schema": inlined_json_schema(MXBIModel),
        "stages": [
            describe_stage(scene)
            for scene in scene_manager.scenes.values()
            if scene is not IDLE
        ],
    }


def describe_stage(scene: type[Scene]) -> dict[str, Any]:
    template: dict[str, Any] | None = None
    if scene.config_template is not None:
        template = json.loads(scene.config_template.read_text(encoding="utf-8"))
    if template is not None:
        rows: dict[str, Any] = template.get(DEFAULT_KEY, {}).get("levels", {})
        levels = [{"id": int(key), **row} for key, row in rows.items()]
    else:
        levels = [{"id": id} for id in scene.level_table.get(DEFAULT_KEY, [])]
    return {
        "name": scene.name(),
        "title": scene.title or scene.name().replace("_", " ").capitalize(),
        "description": scene.description,
        "levels": sorted(levels, key=lambda level: level["id"]),
        "schema": (
            inlined_json_schema(scene.config_model)
            if scene.config_model is not None
            else None
        ),
        "template": template,
    }
