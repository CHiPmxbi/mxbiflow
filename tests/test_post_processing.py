import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from matplotlib.figure import Figure
from pymotego import Heading, Image, KeyValue, Paragraph, Stats, Table

from mxbiflow.infra.camera_recording import TrialMark
from mxbiflow.infra.post_processing import (
    AnimalSummary,
    PostProcessingResult,
    SessionReport,
    SessionSummary,
    StagePostProcessor,
    StageSummary,
    accuracy,
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


def _mark(animal: str, correct: bool | None) -> TrialMark:
    return TrialMark(
        at=datetime(2026, 8, 3, 9, 1, tzinfo=UTC),
        animal=animal,
        stage="detect",
        level=1,
        trial_id=1,
        correct=correct,
    )


class SessionReportTests(unittest.TestCase):
    def test_overview_is_the_fixed_part(self) -> None:
        summary = _summary(
            [
                AnimalSummary(
                    name="m1",
                    rfid_tags=("rfid-1",),
                    total_trials=3,
                    animal_sessions=2,
                    total_duration_seconds=125,
                    stages=[
                        StageSummary(
                            name="detect", trials=3, initial_level=1, final_level=3
                        )
                    ],
                ),
                AnimalSummary(
                    name="m2",
                    total_trials=1,
                    animal_sessions=1,
                    total_duration_seconds=10,
                    stages=[
                        StageSummary(
                            name="detect", trials=1, initial_level=2, final_level=2
                        ),
                        StageSummary(
                            name="hold", trials=0, initial_level=0, final_level=1
                        ),
                    ],
                ),
            ]
        )
        summary.start_at = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
        summary.duration_seconds = 120
        trials = [
            _mark("m1", True),
            _mark("m1", True),
            _mark("m1", False),
            _mark("m2", None),
        ]

        subtitle, stats, animals, heading, details = session_overview(
            summary, trials, "2ac-task"
        )

        date = summary.start_at.astimezone().date().isoformat()
        self.assertEqual(subtitle, Paragraph(f"Session #3 · {date} · 2ac-task"))
        self.assertEqual(
            stats,
            Stats(
                [
                    ("Duration", "2m 0s"),
                    ("Animals", 2),
                    ("Trials", 4),
                    ("Accuracy", "67%"),
                ]
            ),
        )
        assert isinstance(stats, Stats)
        self.assertLessEqual(len(stats.to_json()["items"]), 6)  # type: ignore[arg-type]
        self.assertEqual(
            animals,
            Table(
                ["Animal", "Trials", "Accuracy", "Level change"],
                [
                    ["m1", 3, "67%", "1 -> 3 (+2)"],
                    ["m2", 1, "N/A", "detect 2 (no change); hold 0 -> 1 (+1)"],
                ],
            ),
        )
        self.assertEqual(heading, Heading("Session details"))
        assert isinstance(details, KeyValue)
        self.assertEqual(
            [key for key, _ in details.items],  # type: ignore[misc]
            ["Start", "End", "Experimenter", "Reward type", "Note"],
        )
        self.assertIn(("Note", "Calibration complete"), details.items)

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
        overview.return_value = [Paragraph("Session #3")]
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

        trials = [_mark("m1", True)]
        report = build_session_report(
            session, {"stage": processor, "other": processor}, trials, "task"
        )

        overview.assert_called_once_with(summarize_.return_value, trials, "task")
        self.assertEqual(report.title, "mxbi-1 daily report")
        self.assertEqual(report.summary, "Session #3: 0 animals, 0 trials, N/A")
        self.assertEqual(
            report.blocks,
            [
                Paragraph("Session #3"),
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
            "mxbi-1 daily report", "summary", [Paragraph("x")], {"a.png": PNG}
        )
        session = Mock(send_email=True, session_id=7)

        send_session_report(session, {})

        client.return_value.__enter__.return_value.report.assert_called_once_with(
            "mxbi-1 daily report", [Paragraph("x")], {"a.png": PNG}, summary="summary"
        )

    def test_accuracy_counts_judged_trials(self) -> None:
        trials = [_mark("m1", True), _mark("m2", False), _mark("m2", None)]
        self.assertEqual(accuracy(trials), 0.5)
        self.assertEqual(accuracy(trials, "m2"), 0.0)
        self.assertIsNone(accuracy(trials, "m3"))

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
