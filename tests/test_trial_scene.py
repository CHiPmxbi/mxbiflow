import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from pydantic import BaseModel
from pygame import Event, Surface

from mxbiflow.driver import MXBIModel
from mxbiflow.gameloop.settlement import (
    CountSettlementConfig,
    RateSettlementConfig,
    SettlementAction,
)
from mxbiflow.models.animal import Animal, AnimalBaseInfo, AnimalConfig, StageState
from mxbiflow.models.session import Session, SessionConfig, SessionState
from mxbiflow.scene import TrialScene


class Record(BaseModel):
    animal: AnimalBaseInfo
    correct: bool | None
    aborted: bool
    action: str


class Touch(TrialScene):
    rule: RateSettlementConfig | CountSettlementConfig | None = None
    ended = 0

    def begin(self) -> None:
        self.begun = True

    def end(self) -> None:
        type(self).ended += 1

    def settlement(self) -> RateSettlementConfig | CountSettlementConfig | None:
        return self.rule

    def record(self) -> Record:
        return Record(
            animal=self.info,
            correct=self.correct,
            aborted=self.aborted,
            action=self.action.name,
        )

    def handle_event(self, event: Event) -> None: ...
    def update(self, dt_s: float) -> None: ...
    def draw(self, screen: Surface) -> None: ...


class Next(Touch):
    pass


class TrialSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = AnimalConfig(
            name="a", stage="touch", level=1, stage_order=("touch", "next")
        )
        animal = Animal(
            config=config,
            current_stage_name="touch",
            stages={"touch": StageState(stage_name="touch", level=1)},
        )
        self.session = Session(
            config=SessionConfig(unknown_animal_as="a", animals=(config,)),
            mxbi_config=MXBIModel(),
            state=SessionState(animals={"a": animal}),
        )
        self.session.start(Path(directory.name))
        self.session.set_current_animal("a")
        self.context = SimpleNamespace(
            session=self.session,
            mxbi=SimpleNamespace(aplayer=Mock()),
            publish_trial=Mock(),
            timer=Mock(),
        )
        Touch.rule = None
        Touch.ended = 0

    def trial(self) -> Touch:
        with patch("mxbiflow.core.context._current_mxbiflow", self.context):
            scene = Touch()
        scene.start()
        return scene

    def records(self) -> list[dict[str, Any]]:
        path = self.session.absolute_animal_data_path("a") / "touch" / "result.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_a_finished_trial_is_counted_recorded_published_and_cleaned_up(self):
        scene = self.trial()
        self.assertTrue(scene.running)
        self.assertEqual(scene.info.trial_id, 1)

        scene.finish(True)

        self.assertFalse(scene.running)
        (record,) = self.records()
        self.assertEqual(record["animal"]["trial_id"], 1)
        self.assertEqual(
            (record["correct"], record["aborted"], record["action"]),
            (True, False, "NONE"),
        )
        self.context.publish_trial.assert_called_once()
        self.assertIs(self.context.publish_trial.call_args.kwargs["correct"], True)
        self.context.timer.cancel_all.assert_called_once()
        self.context.mxbi.aplayer.cancel_all.assert_called_once()
        self.assertEqual(Touch.ended, 1)
        stage = self.session.require_current_animal().current_stage
        self.assertEqual((stage.level_counted, stage.level_correct), (1, 1))

    def test_a_trial_ends_once(self) -> None:
        scene = self.trial()

        scene.finish(False)
        scene.finish(True)
        scene.quit()

        self.assertEqual(len(self.records()), 1)
        self.assertEqual(Touch.ended, 1)

    def test_a_trial_the_framework_ends_is_aborted_and_not_settled(self) -> None:
        Touch.rule = CountSettlementConfig(total_levels=2, settlement_cycle=1)
        scene = self.trial()

        scene.quit()

        (record,) = self.records()
        self.assertEqual(
            (record["correct"], record["aborted"], record["action"]),
            (None, True, "NONE"),
        )
        stage = self.session.require_current_animal().current_stage
        self.assertEqual((stage.level, stage.level_counted), (1, 0))

    def test_a_trial_left_out_of_accuracy_does_not_count(self) -> None:
        Touch.rule = RateSettlementConfig(total_levels=2, min_trials=1)
        self.trial().finish(None)

        stage = self.session.require_current_animal().current_stage
        self.assertEqual((stage.level, stage.level_counted), (1, 0))

    def test_the_rate_rule_moves_levels_and_starts_the_counts_again(self) -> None:
        Touch.rule = RateSettlementConfig(
            total_levels=2, min_trials=2, up_rate=0.8, down_rate=0.2
        )
        stage = self.session.require_current_animal().current_stage
        actions: list[str] = []
        levels: list[int] = []
        for correct in (True, True, False, False):
            self.trial().finish(correct)
            actions.append(self.records()[-1]["action"])
            levels.append(stage.level)

        self.assertEqual(actions, ["NONE", "LEVEL_UP", "NONE", "LEVEL_DOWN"])
        self.assertEqual(levels, [1, 2, 2, 1])
        self.assertEqual((stage.level_counted, stage.level_correct), (0, 0))
        # The record keeps the level the trial ran at.
        self.assertEqual(self.records()[1]["animal"]["level"], 1)

    def test_the_count_rule_moves_to_the_next_stage_past_the_last_level(self) -> None:
        Touch.rule = CountSettlementConfig(total_levels=1, settlement_cycle=2)
        self.trial().finish(True)
        self.trial().finish(False)
        scene = self.trial()

        scene.finish(True)

        self.assertIs(scene.action, SettlementAction.NEXT_STAGE)
        animal = self.session.require_current_animal()
        self.assertEqual(animal.current_stage_name, "next")
