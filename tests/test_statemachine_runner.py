import unittest
from typing import Any

from mxbiflow.statemachine.models import Machine
from mxbiflow.statemachine.runner import Trial


def machine(**parts: Any) -> Machine:
    base: dict[str, Any] = {
        "channels": {"inputs": ["lick"], "outputs": ["reward", "laser"]},
        "parameters": [],
        "timers": [],
        "generators": [],
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
        "hold": [],
        "timeout": None,
        "onEntry": [],
        "transitions": [],
    }
    return base | parts


class TrialTests(unittest.TestCase):
    def test_a_counter_reaches_its_limit(self) -> None:
        trial = Trial(
            machine(
                counters=[{"name": "licks", "event": "lick.rise", "limit": 2}],
                states=[
                    state(
                        "wait",
                        transitions=[{"event": "licks.reached", "target": "exit"}],
                    )
                ],
            )
        )

        trial.set_input("lick", True, 10)
        trial.set_input("lick", False, 20)
        self.assertEqual(trial.state, "wait")
        trial.set_input("lick", True, 30)

        self.assertIsNone(trial.state)
        self.assertEqual(trial.log[-1].text, "trial ends")

    def test_a_generator_pulses_its_output_across_states(self) -> None:
        trial = Trial(
            machine(
                generators=[
                    {
                        "name": "flicker",
                        "output": "laser",
                        "delay": 10,
                        "width": 20,
                        "period": 50,
                        "count": 2,
                    }
                ],
                states=[
                    state(
                        "wait",
                        timeout=30,
                        onEntry=[{"start": "flicker"}],
                        transitions=[{"event": "timeout", "target": "give"}],
                    ),
                    state(
                        "give",
                        hold=["reward"],
                        transitions=[{"event": "flicker.done", "target": "exit"}],
                    ),
                ],
            )
        )

        self.assertEqual(trial.outputs(5), set())
        self.assertEqual(trial.outputs(15), {"laser"})
        trial.advance(40)
        self.assertEqual(trial.outputs(40), {"reward"})
        trial.advance(65)
        self.assertEqual(trial.outputs(65), {"reward", "laser"})
        # The last pulse ends at 10 + 50 + 20.
        trial.advance(80)
        self.assertIsNone(trial.state)
        self.assertEqual(trial.outputs(80), set())

    def test_a_group_holds_its_output_in_its_states(self) -> None:
        trial = Trial(
            machine(
                groups=[
                    {"name": "lit", "group": None, "hold": ["laser"], "transitions": []}
                ],
                states=[
                    state(
                        "wait",
                        group="lit",
                        timeout=10,
                        transitions=[{"event": "timeout", "target": "after"}],
                    ),
                    state("after"),
                ],
            )
        )

        self.assertEqual(trial.held(), {"laser"})
        trial.advance(10)
        self.assertEqual(trial.held(), set())

    def test_stopping_ends_the_trial(self) -> None:
        trial = Trial(machine(states=[state("wait", hold=["reward"])]))

        trial.stop(40)

        self.assertIsNone(trial.state)
        self.assertEqual(trial.held(), set())
        self.assertEqual(trial.log[-1].text, "trial stopped")
