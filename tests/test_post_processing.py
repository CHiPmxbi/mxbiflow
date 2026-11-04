import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

from pymotego import Heading, KeyValue, Paragraph, Stats, Table

from mxbiflow.infra.camera_recording import TrialMark
from mxbiflow.infra.post_processing import (
    AnimalSummary,
    SessionReport,
    SessionSummary,
    StageSummary,
    accuracy,
    build_session_report,
    deliver_session_report,
    session_overview,
    summarize,
)


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
                    total_trials=3,
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
    def test_build_is_the_fixed_part(self, summarize_: Mock, overview: Mock) -> None:
        summarize_.return_value = _summary([])
        overview.return_value = [Paragraph("Session #3")]
        session = MagicMock(device_name="mxbi-1")
        trials = [_mark("m1", True)]

        report = build_session_report(session, trials, "task")

        overview.assert_called_once_with(summarize_.return_value, trials, "task")
        self.assertEqual(
            report,
            SessionReport(
                "mxbi-1 daily report",
                "Session #3: 0 animals, 0 trials, N/A",
                [Paragraph("Session #3")],
            ),
        )

    @patch("mxbiflow.infra.post_processing.Client")
    def test_deliver_reports_through_cogmotego(self, client: Mock) -> None:
        report_ = client.return_value.__enter__.return_value.report
        report_.return_value.url = "https://mote/r/1"

        url = deliver_session_report(
            SessionReport("mxbi-1 daily report", "summary", [Paragraph("x")])
        )

        self.assertEqual(url, "https://mote/r/1")
        report_.assert_called_once_with(
            "mxbi-1 daily report", [Paragraph("x")], summary="summary"
        )

    def test_accuracy_counts_judged_trials(self) -> None:
        trials = [_mark("m1", True), _mark("m2", False), _mark("m2", None)]
        self.assertEqual(accuracy(trials), 0.5)
        self.assertEqual(accuracy(trials, "m2"), 0.0)
        self.assertIsNone(accuracy(trials, "m3"))

    @patch("mxbiflow.infra.post_processing.Client")
    def test_deliver_failure_is_raised(self, client: Mock) -> None:
        client.return_value.__enter__.return_value.report.side_effect = RuntimeError(
            "503"
        )
        with self.assertRaises(RuntimeError):
            deliver_session_report(SessionReport("t", "s", []))


if __name__ == "__main__":
    unittest.main()
