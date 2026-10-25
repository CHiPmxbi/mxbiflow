import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from mxbiflow.infra.post_processing import (
    AnimalSummary,
    PostProcessingResult,
    SessionSummary,
    StagePostProcessor,
    StageSummary,
    build_session_report,
    send_session_report,
    session_overview,
    summarize,
)


class StubPostProcessor(StagePostProcessor):
    def __init__(self, result: PostProcessingResult) -> None:
        self.result = result
        self.calls: list[tuple[object, object]] = []

    def process(
        self, session: object, stage_data_paths: object
    ) -> PostProcessingResult:  # type: ignore[override]
        self.calls.append((session, stage_data_paths))
        return self.result


class SummarizeTests(unittest.TestCase):
    def test_session_metadata_is_included(self) -> None:
        start_at = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
        end_at = datetime(2026, 8, 3, 9, 2, tzinfo=UTC)
        session = Mock()
        session.session_id = 3
        session.start_at = start_at
        session.end_at = end_at
        session.experimenter = "Alice"
        session.reward_type.value = "agum_one_fifth"
        session.note = "Calibration complete"
        session.animals = {}

        summary = summarize(session)

        self.assertEqual(summary.session_id, 3)
        self.assertEqual(summary.duration_seconds, 120)
        self.assertEqual(summary.experimenter, "Alice")
        self.assertEqual(summary.reward_type, "agum_one_fifth")
        self.assertEqual(summary.note, "Calibration complete")
        self.assertEqual(summary.total_animals, 0)


class SessionReportTests(unittest.TestCase):
    def test_overview_lists_animals_and_stage_levels(self) -> None:
        summary = SessionSummary(
            session_id=3,
            start_at=None,
            end_at=None,
            duration_seconds=0,
            experimenter="Alice",
            reward_type="agum_one_fifth",
            total_animals=1,
            note="Calibration complete",
            animals=[
                AnimalSummary(
                    name="m1",
                    rfid_id="rfid-1",
                    total_trials=12,
                    animal_sessions=2,
                    total_duration_seconds=125,
                    stages=[
                        StageSummary(
                            name="detect", trials=12, initial_level=1, final_level=3
                        ),
                        StageSummary(
                            name="hold", trials=0, initial_level=2, final_level=2
                        ),
                    ],
                )
            ],
        )

        text = session_overview(summary)

        self.assertIn("Session #3", text)
        self.assertIn("Note: Calibration complete", text)
        self.assertIn("- m1 (rfid-1): 12 trials, 2 sessions, 2m 5s", text)
        self.assertIn("  detect: 12 trials, level 1 -> 3 (+2)", text)
        self.assertIn("  hold: 0 trials, level 2 (no change)", text)

    @patch("mxbiflow.infra.post_processing.session_overview", return_value="overview")
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_dispatches_resolved_stage_paths(
        self,
        _summarize: Mock,
        _overview: Mock,
    ) -> None:
        session = Mock()
        session.data_root = Path("data")
        session.stage_data_paths = {"stage": {"m1": Path("m1/stage")}}
        processor = StubPostProcessor(PostProcessingResult("stage text"))

        report = build_session_report(session, {"stage": processor})

        self.assertEqual(report, "overview\n\nstage text")
        self.assertEqual(processor.calls, [(session, {"m1": Path("data/m1/stage")})])

    @patch("mxbiflow.infra.post_processing.logger.warning")
    @patch("mxbiflow.infra.post_processing.session_overview", return_value="overview")
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_skips_unregistered_stage(
        self,
        _summarize: Mock,
        _overview: Mock,
        warning: Mock,
    ) -> None:
        session = Mock(data_root=Path("data"))
        session.stage_data_paths = {"future": {"m1": Path("m1/future")}}

        report = build_session_report(session, {})

        self.assertEqual(report, "overview")
        warning.assert_called_once_with(
            "skipping stage without post-processor: {}", "future"
        )

    @patch("mxbiflow.infra.post_processing.notify")
    @patch("mxbiflow.infra.post_processing.build_session_report", return_value="text")
    def test_send_notifies_report(self, _build_report: Mock, notify: Mock) -> None:
        session = Mock(send_email=True, session_id=7)
        session.mxbi_config.mxbi_id = "mxbi-1"

        send_session_report(session, {})

        notify.assert_called_once_with("mxbi-1 Daily Report", "text")

    @patch("mxbiflow.infra.post_processing.notify", side_effect=RuntimeError("503"))
    @patch("mxbiflow.infra.post_processing.build_session_report", return_value="text")
    def test_send_failure_is_raised(self, _build_report: Mock, _notify: Mock) -> None:
        with self.assertRaises(RuntimeError):
            send_session_report(Mock(send_email=True), {})

    @patch("mxbiflow.infra.post_processing.notify")
    def test_disabled_report_does_not_send(self, notify: Mock) -> None:
        send_session_report(Mock(send_email=False), {})
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
