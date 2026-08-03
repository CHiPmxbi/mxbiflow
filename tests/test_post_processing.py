import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from mxbiflow.infra.post_processing import summarize


class SummarizeTests(unittest.TestCase):
    @patch("mxbiflow.infra.post_processing.get_mxbiflow")
    def test_session_metadata_is_included(self, get_mxbiflow: Mock) -> None:
        start_at = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
        end_at = datetime(2026, 8, 3, 9, 2, tzinfo=UTC)
        session = get_mxbiflow.return_value.session
        session.session_id = 3
        session.start_at = start_at
        session.end_at = end_at
        session.experimenter = "Alice"
        session.reward_type.value = "agum_one_fifth"
        session.note = "Calibration complete"
        session.animals = {}

        summary = summarize()

        self.assertEqual(summary.session_id, 3)
        self.assertEqual(summary.duration_seconds, 120)
        self.assertEqual(summary.experimenter, "Alice")
        self.assertEqual(summary.reward_type, "agum_one_fifth")
        self.assertEqual(summary.note, "Calibration complete")
        self.assertEqual(summary.total_animals, 0)


if __name__ == "__main__":
    unittest.main()
