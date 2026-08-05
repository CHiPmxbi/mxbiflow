import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pymotego import EmailEmbed

from mxbiflow.infra.post_processing import (
    PostProcessingResult,
    StagePostProcessor,
    build_session_report,
    send_session_report,
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
    @patch("mxbiflow.infra.post_processing.session_overview", return_value="overview")
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_dispatches_resolved_stage_paths(
        self,
        summarize_mock: Mock,
        _overview: Mock,
    ) -> None:
        summarize_mock.return_value = SimpleNamespace(session_id=2, start_at=None)
        session = Mock()
        session.data_root = Path("data")
        session.stage_data_paths = {"stage": {"m1": Path("m1/stage")}}
        embed = EmailEmbed(content_id="plot", filename="plot.png", content=b"png")
        processor = StubPostProcessor(PostProcessingResult("stage html", (embed,)))

        result = build_session_report(session, {"stage": processor})

        self.assertIn("overview", result.html)
        self.assertIn("stage html", result.html)
        self.assertEqual(result.embeds, (embed,))
        self.assertEqual(processor.calls, [(session, {"m1": Path("data/m1/stage")})])

    @patch("mxbiflow.infra.post_processing.logger.warning")
    @patch("mxbiflow.infra.post_processing.session_overview", return_value="overview")
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_skips_unregistered_stage(
        self,
        summarize_mock: Mock,
        _overview: Mock,
        warning: Mock,
    ) -> None:
        summarize_mock.return_value = SimpleNamespace(session_id=2, start_at=None)
        session = Mock(data_root=Path("data"))
        session.stage_data_paths = {"future": {"m1": Path("m1/future")}}

        result = build_session_report(session, {})

        self.assertEqual(result.embeds, ())
        warning.assert_called_once_with(
            "skipping stage without post-processor: {}", "future"
        )

    @patch("mxbiflow.infra.post_processing.get_runtime_state_path")
    @patch("mxbiflow.infra.post_processing.RuntimeStateStore")
    @patch("mxbiflow.infra.post_processing.EmailClient")
    @patch("mxbiflow.infra.post_processing.build_session_report")
    def test_send_uses_and_updates_email_thread(
        self,
        build_report: Mock,
        email_client_cls: Mock,
        runtime_store_cls: Mock,
        _runtime_path: Mock,
    ) -> None:
        embed = EmailEmbed(content_id="plot", filename="plot.png", content=b"png")
        build_report.return_value = PostProcessingResult(
            "<html>report</html>", (embed,)
        )
        session = Mock(send_email=True, session_id=7)
        session.mxbi_config.mxbi_id = "mxbi-1"
        runtime_store_cls.return_value.email_message_id = "previous"
        email_client = email_client_cls.return_value.__enter__.return_value
        email_client.send.return_value.message_id = "current"

        send_session_report(session, {})

        email_client.send.assert_called_once_with(
            subject="mxbi-1 Daily Report",
            html_body="<html>report</html>",
            embeds=[embed],
            in_reply_to="previous",
        )
        runtime_store_cls.return_value.save_email_message_id.assert_called_once_with(
            "current"
        )

    @patch("mxbiflow.infra.post_processing.EmailClient")
    def test_disabled_report_does_not_send(self, email_client_cls: Mock) -> None:
        send_session_report(Mock(send_email=False), {})
        email_client_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
