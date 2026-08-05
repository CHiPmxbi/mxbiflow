import os
import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from mxbiflow.infra.post_processing import (
    AnimalSummary,
    SessionSummary,
    StageSummary,
)
from mxbiflow.ui.components.countdown import AutoAcceptCountdown
from mxbiflow.ui.session_summary_panel import (
    SessionSummaryPanel,
    run_session_summary,
)


def make_summary(*, with_animals: bool = True) -> SessionSummary:
    animals = (
        [
            AnimalSummary(
                name="mouse-1",
                rfid_id="rfid-1",
                total_trials=12,
                animal_sessions=2,
                total_duration_seconds=125,
                stages=[
                    StageSummary(
                        name="discrimination",
                        trials=12,
                        initial_level=1,
                        final_level=3,
                    )
                ],
            )
        ]
        if with_animals
        else []
    )
    return SessionSummary(
        session_id=7,
        start_at=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 8, 3, 10, 1, 2, tzinfo=UTC),
        duration_seconds=3662,
        experimenter="Alice",
        reward_type="agum_one_fifth",
        total_animals=len(animals),
        note="Daily calibration complete",
        animals=animals,
    )


class SessionSummaryPanelTests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def test_summary_fields_and_tables_are_displayed(self) -> None:
        panel = SessionSummaryPanel(make_summary())

        labels = {label.text() for label in panel.findChildren(QLabel)}
        self.assertTrue(
            {
                "7",
                "1h 1m 2s",
                "Alice",
                "agum_one_fifth",
                "Daily calibration complete",
            }.issubset(labels)
        )

        tables = {
            table.accessibleName(): table for table in panel.findChildren(QTableWidget)
        }
        animals_table = tables["Animal session summary"]
        stages_table = tables["Stage session summary"]
        self.assertEqual(animals_table.rowCount(), 1)
        animal_name = animals_table.item(0, 0)
        animal_duration = animals_table.item(0, 4)
        assert animal_name is not None
        assert animal_duration is not None
        self.assertEqual(animal_name.text(), "mouse-1")
        self.assertEqual(animal_duration.text(), "2m 5s")
        self.assertEqual(stages_table.rowCount(), 1)
        stage_name = stages_table.item(0, 1)
        final_level = stages_table.item(0, 4)
        assert stage_name is not None
        assert final_level is not None
        self.assertEqual(stage_name.text(), "discrimination")
        self.assertEqual(final_level.text(), "3")
        self.assertFalse(
            bool(animals_table.editTriggers() & QTableWidget.EditTrigger.DoubleClicked)
        )

    def test_empty_animal_and_stage_tables_are_supported(self) -> None:
        panel = SessionSummaryPanel(make_summary(with_animals=False))
        tables = panel.findChildren(QTableWidget)

        self.assertEqual(len(tables), 2)
        self.assertTrue(all(table.rowCount() == 0 for table in tables))

    def test_continue_accepts_and_cancel_rejects(self) -> None:
        panel = SessionSummaryPanel(make_summary())
        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        self.assertEqual(buttons["Cancel"].minimumHeight(), 0)
        self.assertEqual(buttons["Continue"].minimumHeight(), 0)
        self.assertFalse(buttons["Continue"].isDefault())

        QTest.mouseClick(buttons["Continue"], Qt.MouseButton.LeftButton)
        self.assertEqual(panel.result(), SessionSummaryPanel.DialogCode.Accepted)

        panel = SessionSummaryPanel(make_summary())
        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        QTest.mouseClick(buttons["Cancel"], Qt.MouseButton.LeftButton)
        self.assertEqual(panel.result(), SessionSummaryPanel.DialogCode.Rejected)

    def test_countdown_starts_at_30_seconds_and_accepts_on_timeout(self) -> None:
        panel = SessionSummaryPanel(make_summary())
        countdown = panel.findChild(AutoAcceptCountdown)
        assert countdown is not None

        panel.show()
        self.application.processEvents()
        countdown_label = countdown.findChild(QLabel)
        assert countdown_label is not None
        self.assertEqual(countdown_label.text(), "Auto: 30s")
        self.assertTrue(countdown.is_active())

        countdown.timeout.emit()

        self.assertEqual(panel.result(), SessionSummaryPanel.DialogCode.Accepted)
        self.assertFalse(countdown.is_active())

    def test_stopped_countdown_keeps_manual_actions_available(self) -> None:
        panel = SessionSummaryPanel(make_summary())
        countdown = panel.findChild(AutoAcceptCountdown)
        assert countdown is not None
        panel.show()
        self.application.processEvents()

        QTest.mouseClick(countdown.stop_button, Qt.MouseButton.LeftButton)

        self.assertFalse(countdown.is_active())
        self.assertEqual(panel.result(), SessionSummaryPanel.DialogCode.Rejected)
        continue_button = next(
            button
            for button in panel.findChildren(QPushButton)
            if button.text() == "Continue"
        )
        QTest.mouseClick(continue_button, Qt.MouseButton.LeftButton)
        self.assertEqual(panel.result(), SessionSummaryPanel.DialogCode.Accepted)

    def test_tables_show_two_rows_and_scroll_when_data_overflows(self) -> None:
        summary = make_summary()
        animal = summary.animals[0]
        summary.animals = [
            animal.model_copy(
                update={
                    "name": f"mouse-{index}",
                    "stages": [
                        animal.stages[0].model_copy(update={"name": f"stage-{index}"})
                    ],
                }
            )
            for index in range(4)
        ]
        summary.total_animals = len(summary.animals)
        panel = SessionSummaryPanel(summary)
        panel.show()
        self.application.processEvents()

        tables = panel.findChildren(QTableWidget)
        self.assertEqual(len(tables), 2)
        for table in tables:
            two_rows_height = (
                table.horizontalHeader().sizeHint().height()
                + 2 * table.verticalHeader().defaultSectionSize()
                + table.frameWidth() * 2
            )
            self.assertEqual(table.height(), two_rows_height)
            self.assertGreater(table.verticalScrollBar().maximum(), 0)

        panel.close()

    @patch("mxbiflow.ui.session_summary_panel.SessionSummaryPanel")
    @patch("mxbiflow.ui.session_summary_panel.summarize")
    @patch("mxbiflow.ui.session_summary_panel.require_application")
    def test_run_session_summary_returns_dialog_decision(
        self,
        require_application: Mock,
        summarize: Mock,
        panel_class: Mock,
    ) -> None:
        panel_class.return_value.exec.side_effect = [
            SessionSummaryPanel.DialogCode.Accepted,
            SessionSummaryPanel.DialogCode.Rejected,
        ]

        self.assertTrue(run_session_summary())
        self.assertFalse(run_session_summary())

        self.assertEqual(require_application.call_count, 2)
        self.assertEqual(summarize.call_count, 2)
        self.assertEqual(panel_class.call_count, 2)


if __name__ == "__main__":
    unittest.main()
