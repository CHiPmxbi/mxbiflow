import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pygame
from test_session import make_session

from mxbiflow.infra.camera_recording import TrialMark
from mxbiflow.infra.run_end import (
    SEND_REPORT,
    SUMMARY_BROADCAST,
    UPLOAD_RECORDING,
    RunEnd,
    begin_run,
    run_summary,
)
from mxbiflow.ui.run_end_screen import draw, show_run_end


def mark(correct: bool | None) -> TrialMark:
    return TrialMark(
        at=datetime.now(UTC),
        animal="animal-1",
        stage="vocalization_discriminate",
        level=2,
        trial_id=1,
        correct=correct,
    )


class RunEndTests(unittest.TestCase):
    def test_reports_every_change_and_the_final_state(self) -> None:
        client = Mock()
        steps = RunEnd([UPLOAD_RECORDING, SEND_REPORT], client=client)

        steps.start(UPLOAD_RECORDING, done=0, total=10, unit=True)
        steps.done(UPLOAD_RECORDING)
        steps.start(SEND_REPORT)
        steps.fail([SEND_REPORT], "offline", retry=False)
        steps.close()

        sent = [call.kwargs for call in client.patch_status.call_args_list]
        self.assertEqual([s["state"] for s in sent], ["finishing"] * 5 + ["failed"])
        first = sent[0]["steps"]
        self.assertEqual([s.state for s in first], ["waiting", "waiting"])
        self.assertEqual(first[0].label, "Upload the camera recording")
        report = sent[-1]["steps"][1]
        self.assertEqual(
            (report.state, report.reason, report.retry), ("failed", "offline", False)
        )
        client.close.assert_called_once_with()

    def test_all_done_ends_idle(self) -> None:
        client = Mock()
        steps = RunEnd([SEND_REPORT], client=client)
        steps.done(SEND_REPORT, url="https://mote/r/1")
        steps.close()

        last = client.patch_status.call_args.kwargs
        self.assertEqual(last["state"], "idle")
        self.assertEqual(last["steps"][0].url, "https://mote/r/1")

    def test_byte_progress_is_throttled(self) -> None:
        client = Mock()
        steps = RunEnd([UPLOAD_RECORDING], client=client, interval_s=60)
        steps.start(UPLOAD_RECORDING, done=0, total=10, unit=True)
        for done in range(1, 10):
            steps.progress(UPLOAD_RECORDING, done)

        self.assertEqual(client.patch_status.call_count, 2)
        self.assertEqual(steps.steps[0].done, 9)

    def test_an_absent_cogmotego_is_not_an_error(self) -> None:
        client = Mock()
        client.patch_status.side_effect = ConnectionError("refused")
        steps = RunEnd([SEND_REPORT], client=client)
        steps.done(SEND_REPORT)
        steps.close()

        self.assertEqual(steps.steps[0].state, "done")

    @patch("mxbiflow.infra.run_end.Broadcast")
    @patch("mxbiflow.infra.run_end.Client")
    def test_begin_run_drops_the_last_steps_and_summary(
        self, client: Mock, broadcast: Mock
    ) -> None:
        session = make_session()
        session.state.start_at = datetime(2026, 10, 27, 9, tzinfo=UTC)

        begin_run(session)

        client.return_value.__enter__.return_value.patch_status.assert_called_once_with(
            state="running", started_at=session.start_at, steps=None
        )
        broadcast.return_value.__enter__.return_value.delete.assert_called_once_with(
            SUMMARY_BROADCAST
        )


class RunSummaryTests(unittest.TestCase):
    def test_summarizes_trials_accuracy_and_levels(self) -> None:
        session = make_session()
        start = datetime(2026, 10, 27, 9, tzinfo=UTC)
        session.state.start_at = start
        session.state.end_at = start + timedelta(minutes=30)
        session.animals["animal-1"].current_stage.level = 3

        summary = run_summary(
            session, [mark(True), mark(False), mark(True), mark(None)]
        )

        self.assertEqual(summary.duration_seconds, 1800)
        [animal] = summary.animals
        self.assertAlmostEqual(animal.accuracy or 0, 2 / 3)
        [stage] = animal.stages
        self.assertEqual((stage.initial_level, stage.final_level), (2, 3))
        self.assertIsNone(run_summary(session, []).animals[0].accuracy)


class RunEndScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    def test_draws_the_summary_and_every_step_state(self) -> None:
        steps = RunEnd([UPLOAD_RECORDING, SEND_REPORT], client=Mock())
        steps.start(UPLOAD_RECORDING, done=5e6, total=2e7, unit=True)
        steps.fail([SEND_REPORT], "offline", retry=False)
        pygame.display.init()
        pygame.font.init()
        try:
            screen = pygame.display.set_mode((800, 480))
            draw(screen, run_summary(make_session(), []), steps.steps, finished=False)
        finally:
            pygame.display.quit()

    def test_runs_the_work_and_returns_after_the_hold(self) -> None:
        work = Mock()
        show_run_end(
            run_summary(make_session(), []),
            RunEnd([], client=Mock()),
            work,
            size=(320, 240),
            fullscreen=False,
            hold_s=0,
        )

        work.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
