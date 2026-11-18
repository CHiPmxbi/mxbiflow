"""The experiment format shared with cogforge: stages of trial state machines.

`models.py` is generated from `experiment.schema.json`, which is copied from cogforge
(`schema/experiment.schema.json`). Never edit it by hand: copy the new schema over and
run `uv run datamodel-codegen`.
"""

from pathlib import Path

from .models import Experiment

__all__ = ["Experiment", "load_experiment"]


def load_experiment(path: Path) -> Experiment:
    """Read an experiment JSON file written by cogforge."""
    return Experiment.model_validate_json(path.read_text(encoding="utf-8"))
