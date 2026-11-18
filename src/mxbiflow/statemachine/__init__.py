"""The experiment format shared with cogforge: stages of trial state machines.

`models.py` is generated from `experiment.schema.json`, which is copied from cogforge
(`schema/experiment.schema.json`). Never edit it by hand: copy the new schema over and
run `uv run datamodel-codegen`.

An experiment runs by registering its stages' scenes::

    scene_manager.register(machine_scenes(load_experiment(path)))

A stage can also be written in Python, with states and transitions added by name and
Python hooks for what the data cannot say (`builder`)::

    scene_manager.register(stage_scenes(stage))

`runner` and `host` are ports of cogforge's `simulate.ts` and `host.ts` and pass its
conformance cases (`tests/fixtures/conformance`).
"""

from pathlib import Path

from .builder import StageBuilder, stage_scenes
from .models import Experiment
from .scene import MachineScene, machine_scenes

__all__ = [
    "Experiment",
    "MachineScene",
    "StageBuilder",
    "load_experiment",
    "machine_scenes",
    "stage_scenes",
]


def load_experiment(path: Path) -> Experiment:
    """Read an experiment JSON file written by cogforge."""
    return Experiment.model_validate_json(path.read_text(encoding="utf-8"))
