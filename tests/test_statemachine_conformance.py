"""cogforge's conformance cases: the runner and host logic against its TypeScript.

``tests/fixtures/conformance/cases.json`` is copied from cogforge
(``conformance/cases.json``, written by ``bun run conformance``).
"""

import json
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mxbiflow.statemachine.host import Progress, draw_trial, outcome_of, settle
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
    }


def run_draw(case: dict[str, Any]) -> dict[str, Any]:
    experiment = Experiment.model_validate(case["experiment"])
    animal = next(a for a in experiment.animals if a.name == case["animal"])
    numbers = iter(case["random"])
    draw = draw_trial(
        experiment,
        animal.values,
        Progress(**case["progress"]),
        lambda: next(numbers, 0),
    )
    return asdict(draw)


def run_settle(case: dict[str, Any]) -> list[dict[str, Any]]:
    experiment = Experiment.model_validate(case["experiment"])
    progress = Progress(**case["progress"])
    results: list[dict[str, Any]] = []
    for outcome in case["outcomes"]:
        progress, action = settle(experiment, progress, outcome)
        results.append({"progress": asdict(progress), "action": action})
    return results


RUN = {"trial": run_trial, "draw": run_draw, "settle": run_settle}


class ConformanceTests(unittest.TestCase):
    def test_every_case(self) -> None:
        self.assertGreater(len(CASES), 0)
        for case in CASES:
            with self.subTest(case["name"]):
                self.assertEqual(RUN[case["kind"]](case), case["expected"])
