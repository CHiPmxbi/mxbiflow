import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from matplotlib.figure import Figure
from pymotego import Heading, Image, KeyValue, Paragraph, Table

from mxbiflow.infra.post_processing import (
    AnimalSummary,
    PostProcessingResult,
    SessionReport,
    SessionSummary,
    StagePostProcessor,
    StageSummary,
    build_session_report,
    figure_png,
    send_session_report,
    session_overview,
    summarize,
)

PNG = b"\x89PNG\r\n\x1a\n-figure"


class StubPostProcessor(StagePostProcessor):
    def __init__(self, result: PostProcessingResult) -> None:
        self.result = result
        self.calls: list[tuple[object, object]] = []

    def process(
        self, session: object, stage_data_paths: object
    ) -> PostProcessingResult:  # type: ignore[override]
        self.calls.append((session, stage_data_paths))
        return self.result


def _summary(animals: list[AnimalSummary]) -> SessionSummary:
    return SessionSummary(
        session_id=3,
        start_at=None,
        end_at=None,
        duration_seconds=0,
        experimenter="Alice",
        reward_type="agum_one_fifth",
        total_animals=len(animals),
        note="Calibration complete",
        animals=animals,
    )


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
        summary = _summary(
            [
                AnimalSummary(
                    name="m1",
                    rfid_tags=("rfid-1",),
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
            ]
        )

        heading, details, animals, stages = session_overview(summary)

        self.assertEqual(heading, Heading("Session #3"))
        assert isinstance(details, KeyValue)
        self.assertIn(("Note", "Calibration complete"), details.items)
        self.assertEqual(
            animals,
            Table(
                ["Animal", "RFID", "Trials", "Sessions", "Duration"],
                [["m1", "rfid-1", 12, 2, "2m 5s"]],
                caption="Animals (1)",
            ),
        )
        self.assertEqual(
            stages,
            Table(
                ["Animal", "Stage", "Trials", "Level"],
                [
                    ["m1", "detect", 12, "level 1 -> 3 (+2)"],
                    ["m1", "hold", 0, "level 2 (no change)"],
                ],
            ),
        )

    def test_overview_without_animals_has_no_tables(self) -> None:
        blocks = session_overview(_summary([]))
        self.assertFalse(any(isinstance(block, Table) for block in blocks))

    @patch("mxbiflow.infra.post_processing.session_overview")
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_dispatches_resolved_stage_paths_and_prefixes_images(
        self,
        summarize_: Mock,
        overview: Mock,
    ) -> None:
        summarize_.return_value = _summary([])
        overview.return_value = [Heading("Session #3")]
        session = MagicMock()
        session.device_name = "mxbi-1"
        session.data_root = Path("data")
        session.stage_data_paths = {
            "stage": {"m1": Path("m1/stage")},
            "other": {"m1": Path("m1/other")},
        }
        section = PostProcessingResult(
            [Heading("Stage"), Paragraph("ok"), Image("accuracy.png", "Accuracy")],
            {"accuracy.png": PNG},
        )
        processor = StubPostProcessor(section)

        report = build_session_report(session, {"stage": processor, "other": processor})

        self.assertEqual(report.title, "mxbi-1 Daily Report")
        self.assertEqual(report.summary, "Session #3: 0 animals, 0 trials, N/A")
        self.assertEqual(
            report.blocks,
            [
                Heading("Session #3"),
                Heading("Stage"),
                Paragraph("ok"),
                Image("s0-accuracy.png", "Accuracy"),
                Heading("Stage"),
                Paragraph("ok"),
                Image("s1-accuracy.png", "Accuracy"),
            ],
        )
        self.assertEqual(
            report.images, {"s0-accuracy.png": PNG, "s1-accuracy.png": PNG}
        )
        self.assertEqual(processor.calls[0], (session, {"m1": Path("data/m1/stage")}))

    @patch("mxbiflow.infra.post_processing.logger.warning")
    @patch("mxbiflow.infra.post_processing.session_overview", return_value=[])
    @patch("mxbiflow.infra.post_processing.summarize")
    def test_build_skips_unregistered_stage(
        self,
        summarize_: Mock,
        _overview: Mock,
        warning: Mock,
    ) -> None:
        summarize_.return_value = _summary([])
        session = MagicMock(data_root=Path("data"))
        session.stage_data_paths = {"future": {"m1": Path("m1/future")}}

        report = build_session_report(session, {})

        self.assertEqual(report.blocks, [])
        warning.assert_called_once_with(
            "skipping stage without post-processor: {}", "future"
        )

    @patch("mxbiflow.infra.post_processing.Client")
    @patch("mxbiflow.infra.post_processing.build_session_report")
    def test_send_reports_through_cogmotego(self, build: Mock, client: Mock) -> None:
        build.return_value = SessionReport(
            "mxbi-1 Daily Report", "summary", [Paragraph("x")], {"a.png": PNG}
        )
        session = Mock(send_email=True, session_id=7)

        send_session_report(session, {})

        client.return_value.__enter__.return_value.report.assert_called_once_with(
            "mxbi-1 Daily Report", [Paragraph("x")], {"a.png": PNG}, summary="summary"
        )

    @patch("mxbiflow.infra.post_processing.Client")
    @patch("mxbiflow.infra.post_processing.build_session_report")
    def test_send_failure_is_raised(self, build: Mock, client: Mock) -> None:
        build.return_value = SessionReport("t", "s", [], {})
        client.return_value.__enter__.return_value.report.side_effect = RuntimeError(
            "503"
        )
        with self.assertRaises(RuntimeError):
            send_session_report(Mock(send_email=True), {})

    @patch("mxbiflow.infra.post_processing.Client")
    def test_disabled_report_does_not_send(self, client: Mock) -> None:
        send_session_report(Mock(send_email=False), {})
        client.assert_not_called()

    def test_figure_png(self) -> None:
        figure = Figure(figsize=(2, 1))
        figure.add_subplot().plot([0, 1], [1, 0])
        self.assertTrue(figure_png(figure).startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
