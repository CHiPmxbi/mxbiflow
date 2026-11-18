"""The experiment format shared with cogforge: stages of trial state machines.

`models.py` is generated from `experiment.schema.json`, which is copied from cogforge
(`schema/experiment.schema.json`). Never edit it by hand: copy the new schema over and
run `uv run datamodel-codegen`.

The format has the trial only: a stage is a machine and the outcomes of its states.
Which values a trial gets and how an animal moves between levels is the host's Python.

A stage written in Python is a class with its machine (`machine`) and each trial's
values (`scene.MachineTrial`)::

    scene_manager.register([Touch])

The stages of a cogforge file run with their parameters' defaults::

    scene_manager.register(machine_scenes(load_experiment(path)))

`mxbiflow eject experiment.json` writes a file as Python stages (`eject`).

`runner` and `host` are ports of cogforge's `simulate.ts` and `host.ts` and pass its
conformance cases (`tests/fixtures/conformance`).
"""

from pathlib import Path

from .machine import Machine, TrialParams
from .models import Experiment
from .scene import MachineScene, MachineTrial, machine_scenes, on_enter

__all__ = [
    "Experiment",
    "Machine",
    "MachineScene",
    "MachineTrial",
    "TrialParams",
    "load_experiment",
    "machine_scenes",
    "on_enter",
]


def load_experiment(path: Path) -> Experiment:
    """Read an experiment JSON file written by cogforge."""
    return Experiment.model_validate_json(path.read_text(encoding="utf-8"))
