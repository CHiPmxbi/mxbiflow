import unittest
from typing import Any

from mxbiflow.statemachine.models import Machine
from mxbiflow.statemachine.runner import Edge, Trial, TrialError


def machine(**parts: Any) -> Machine:
    base: dict[str, Any] = {
        "channels": {"inputs": ["lick"], "outputs": ["reward", "laser"]},
        "parameters": [],
        "timers": [],
        "counters": [],
        "start": "wait",
        "groups": [],
        "states": [],
        "layout": {},
        "screen": {"width": 100, "height": 100},
        "stimuli": [],
    }
    return Machine.model_validate(base | parts)


def state(name: str, **parts: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "group": None,
        "onEntry": [],
        "onExit": [],
        "transitions": [],
    }
    return base | parts


def on(event: str, target: str | None, *actions: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "target": target, "actions": list(actions)}


class TrialTests(unittest.TestCase):
    def test_a_counter_reaches_its_limit(self) -> None:
        trial = Trial(
            machine(
                counters=[{"name": "licks", "event": "lick.rise", "limit": 2}],
                states=[state("wait", transitions=[on("licks.reached", "exit")])],
            )
        )

        trial.set_input("lick", True, 10)
        trial.set_input("lick", False, 20)
        self.assertEqual(trial.state, "wait")
        trial.set_input("lick", True, 30)

        self.assertIsNone(trial.state)
        self.assertEqual(trial.log[-1].text, "trial ends")

    def test_a_timed_edge_outlasts_its_state(self) -> None:
        trial = Trial(
            machine(
                timers=[{"name": "wait_time", "time": 30}],
                states=[
                    state(
                        "wait",
                        onEntry=[
                            {"start": "wait_time"},
                            {"high": "laser", "after": 10},
                            {"low": "laser", "after": 50},
                        ],
                        transitions=[on("wait_time.done", "give")],
                    ),
                    state("give", onEntry=[{"high": "reward"}]),
                ],
            )
        )

        self.assertEqual(trial.high(), set())
        trial.advance(15)
        self.assertEqual(trial.high(), {"laser"})
        trial.advance(40)
        self.assertEqual(trial.high(), {"laser", "reward"})
        trial.advance(60)
        self.assertEqual(trial.high(), {"reward"})
        self.assertEqual(
            trial.changes,
            [
                Edge(10, "laser", True),
                Edge(30, "reward", True),
                Edge(50, "laser", False),
            ],
        )

    def test_a_group_acts_only_across_its_boundary(self) -> None:
        trial = Trial(
            machine(
                timers=[{"name": "t", "time": 10}],
                groups=[
                    {
                        "name": "lit",
                        "group": None,
                        "onEntry": [{"high": "laser"}],
                        "onExit": [{"low": "laser"}],
                        "transitions": [],
                    }
                ],
                states=[
                    state(
                        "wait",
                        group="lit",
                        onEntry=[{"start": "t"}],
                        transitions=[on("t.done", "after")],
                    ),
                    state("after"),
                ],
            )
        )

        self.assertEqual(trial.high(), {"laser"})
        trial.advance(10)
        self.assertEqual(trial.high(), set())

    def test_an_error_ends_the_trial_with_outputs_low(self) -> None:
        trial = Trial(
            machine(
                timers=[{"name": "t", "time": 10}],
                states=[
                    state(
                        "wait",
                        onEntry=[{"high": "reward"}, {"start": "t"}],
                        transitions=[on("lick.rise", None, {"start": "t"})],
                    )
                ],
            )
        )

        trial.set_input("lick", True, 5)

        self.assertIsNone(trial.state)
        self.assertIs(trial.error, TrialError.TIMER_RUNNING)
        self.assertEqual(trial.error_detail, "start t: the timer is running")
        self.assertEqual(trial.high(), set())

    def test_stopping_ends_the_trial(self) -> None:
        trial = Trial(machine(states=[state("wait", onEntry=[{"high": "reward"}])]))

        trial.stop(40)

        self.assertIsNone(trial.state)
        self.assertEqual(trial.high(), set())
        self.assertIsNone(trial.error)
        self.assertEqual(trial.log[-1].text, "reward low")
        self.assertEqual(trial.changes[-1], Edge(40, "reward", False))
