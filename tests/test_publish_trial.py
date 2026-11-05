import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import BaseModel
from test_session import make_session

from mxbiflow.core.context import MXBIFlow
from mxbiflow.infra.camera_recording import segment_start, write_subtitles
from mxbiflow.infra.run_end import run_summary
from mxbiflow.models import AnimalBaseInfo


class Result(BaseModel):
    animal: AnimalBaseInfo


class Plain(BaseModel):
    trial: int


class PublishTrialMarkTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("mxbiflow.core.context.is_offline", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = make_session()
        self.session.set_current_animal("animal-1")
        self.flow = MXBIFlow(self.session, Mock())
        self.session.add_trial()

    def level_up_trial(self) -> None:
        """Publish as a stage does: the base info is from the trial's start."""
        animal = self.session.require_current_animal()
        result = Result(animal=animal.base_info)
        self.session.level_up()
        self.flow.publish_trial(result, correct=True)

    def test_a_level_up_trial_keeps_the_level_it_started_with(self) -> None:
        self.level_up_trial()

        mark = self.flow.trials[0]
        self.assertEqual(mark.stage, "vocalization_discriminate")
        self.assertEqual(mark.level, 2)
        self.assertEqual(mark.trial_id, 1)

    def test_the_subtitle_shows_the_starting_level(self) -> None:
        self.level_up_trial()
        mark = self.flow.trials[0]

        with tempfile.TemporaryDirectory() as directory:
            segment = Path(directory) / (
                (mark.at - timedelta(seconds=1))
                .astimezone()
                .strftime("%Y-%m-%d_%H-%M-%S-%f.mp4")
            )
            self.assertIsNotNone(segment_start(segment))
            written = write_subtitles([segment], [mark], capture_latency=timedelta(0))
            text = written[0].read_text()

        self.assertIn(
            "trial 1 | animal-1 | vocalization_discriminate@2 | correct", text
        )

    def test_the_run_summary_counts_the_trial_and_the_level_change(self) -> None:
        self.level_up_trial()

        animal = run_summary(self.session, self.flow.trials).animals[0]

        self.assertEqual(animal.trials, 1)
        self.assertEqual(animal.accuracy, 1.0)
        self.assertEqual(animal.stages[0].initial_level, 2)
        self.assertEqual(animal.stages[0].final_level, 3)

    def test_a_record_without_base_info_uses_the_session(self) -> None:
        for record in ({"trial": 1}, Plain(trial=1)):
            with self.subTest(record=type(record).__name__):
                flow = MXBIFlow(self.session, Mock())
                level = self.session.level_up()

                flow.publish_trial(record, correct=None)

                mark = flow.trials[0]
                self.assertEqual(mark.level, level)
                self.assertEqual(mark.trial_id, 1)
                self.assertEqual(mark.stage, "vocalization_discriminate")


if __name__ == "__main__":
    unittest.main()
