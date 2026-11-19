"""cogforge's conformance cases: the runner against its TypeScript.

``tests/fixtures/conformance/cases.json`` is copied from cogforge
(``conformance/cases.json``, written by ``bun run conformance``).
"""

import json
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mxbiflow.statemachine.host import outcome_of
from mxbiflow.statemachine.models import Experiment
from mxbiflow.statemachine.runner import Trial

CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "conformance" / "cases.json").read_text(
        encoding="utf-8"
    )
)


def run_trial(case: dict[str, Any]) -> dict[str, Any]:
    stage = Experiment.model_validate(case["experiment"]).stages[case["stage"]]
    trial = Trial(stage.machine, case["initial"], 0, dict(case["values"]))
    for step in case["steps"]:
        if "touch" in step:
            x, y = step["touch"]
            trial.touch(x, y, step["t"])
        else:
            trial.set_input(step["input"], step["high"], step["t"])
    trial.advance(case["end"])
    return {
        "visited": [asdict(visit) for visit in trial.visited],
        "state": trial.state,
        "shown": trial.shown,
        "outcome": outcome_of(stage, trial),
        "edges": [asdict(edge) for edge in trial.changes],
        "error": trial.error,
    }


class ConformanceTests(unittest.TestCase):
    def test_every_case(self) -> None:
        self.assertGreater(len(CASES), 0)
        for case in CASES:
            with self.subTest(case["name"]):
                self.assertEqual(case["kind"], "trial")
                self.assertEqual(run_trial(case), case["expected"])
