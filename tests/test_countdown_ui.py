import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QSpinBox

from mxbiflow.core.path import get_mxbi_panel_config_path, set_base_path
from mxbiflow.models.panel import MXBIPanelConfig
from mxbiflow.scene import SceneManager
from mxbiflow.ui.components.countdown import AutoAcceptCountdown
from mxbiflow.ui.experiment_panel import ExperimentPanel
from mxbiflow.ui.mxbi_panel import MXBIPanel


class TestCountdown(AutoAcceptCountdown):
    def tick(self) -> None:
        self._tick()


def find_countdown(panel: MXBIPanel | ExperimentPanel) -> AutoAcceptCountdown:
    countdown = panel.findChild(AutoAcceptCountdown)
    if countdown is None:
        raise AssertionError("Auto-accept countdown widget not found in panel")
    return countdown


class AutoAcceptCountdownTests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def test_only_stop_button_stops_countdown(self) -> None:
        countdown = AutoAcceptCountdown()
        countdown.start(10)
        label = countdown.findChild(QLabel)
        self.assertIsNotNone(label)
        if label is None:
            raise AssertionError("Remaining-time label not found in countdown widget")

        QTest.mouseClick(countdown, Qt.MouseButton.LeftButton)
        self.assertTrue(countdown.is_active())

        QTest.mouseClick(countdown.stop_button, Qt.MouseButton.LeftButton)
        self.assertFalse(countdown.is_active())
        self.assertFalse(countdown.isHidden())
        self.assertEqual(label.text(), "Auto: 10s")
        self.assertFalse(countdown.stop_button.isEnabled())

        countdown.start(5)
        self.assertTrue(countdown.is_active())
        self.assertEqual(label.text(), "Auto: 5s")
        self.assertTrue(countdown.stop_button.isEnabled())

    def test_countdowns_are_independent_and_emit_once(self) -> None:
        first = TestCountdown()
        second = TestCountdown()
        first_timeout = Mock()
        second_timeout = Mock()
        first.timeout.connect(first_timeout)
        second.timeout.connect(second_timeout)

        first.start(1)
        second.start(2)
        first.tick()

        self.assertFalse(first.is_active())
        self.assertTrue(second.is_active())
        first_timeout.assert_called_once_with()
        second_timeout.assert_not_called()

        first.tick()
        self.assertFalse(first.is_active())
        first_timeout.assert_called_once_with()

        second.stop()


class PanelCountdownTests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._home_patch = patch.dict(
            os.environ, {"HOME": self._temporary_directory.name}
        )
        self._home_patch.start()
        set_base_path(Path(self._temporary_directory.name))

    def tearDown(self) -> None:
        self.application.processEvents()
        self._home_patch.stop()
        self._temporary_directory.cleanup()

    def test_panels_start_counting_only_when_shown(self) -> None:
        mxbi_panel = MXBIPanel()
        experiment_panel = ExperimentPanel(SceneManager())
        mxbi_countdown = find_countdown(mxbi_panel)
        experiment_countdown = find_countdown(experiment_panel)

        self.assertFalse(mxbi_countdown.is_active())
        self.assertFalse(experiment_countdown.is_active())

        mxbi_panel.show()
        self.application.processEvents()
        self.assertTrue(mxbi_countdown.is_active())
        self.assertFalse(experiment_countdown.is_active())

        mxbi_panel.close()
        experiment_panel.show()
        self.application.processEvents()
        self.assertFalse(mxbi_countdown.is_active())
        self.assertTrue(experiment_countdown.is_active())

        experiment_panel.close()

    def test_clicking_panel_or_save_does_not_stop_countdown(self) -> None:
        panel = MXBIPanel()
        countdown = find_countdown(panel)
        panel.show()
        self.application.processEvents()

        QTest.mouseClick(panel, Qt.MouseButton.LeftButton)
        self.assertTrue(countdown.is_active())

        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)
        self.assertTrue(countdown.is_active())

        QTest.mouseClick(countdown.stop_button, Qt.MouseButton.LeftButton)
        self.assertFalse(countdown.is_active())
        self.assertTrue(countdown.isVisible())
        panel.close()

    def test_panel_actions_use_dialog_result_codes(self) -> None:
        mxbi_panel = MXBIPanel()
        mxbi_panel.show()
        self.application.processEvents()
        QTest.mouseClick(mxbi_panel.cancel_button, Qt.MouseButton.LeftButton)
        self.assertEqual(mxbi_panel.result(), QDialog.DialogCode.Rejected)

        mxbi_panel = MXBIPanel()
        mxbi_panel.show()
        self.application.processEvents()
        QTest.mouseClick(mxbi_panel.continue_button, Qt.MouseButton.LeftButton)
        self.assertEqual(mxbi_panel.result(), QDialog.DialogCode.Accepted)

        experiment_panel = ExperimentPanel(SceneManager())
        cancel_button = next(
            button
            for button in experiment_panel.findChildren(QPushButton)
            if button.text() == "Cancel"
        )
        experiment_panel.show()
        self.application.processEvents()
        QTest.mouseClick(cancel_button, Qt.MouseButton.LeftButton)
        self.assertEqual(experiment_panel.result(), QDialog.DialogCode.Rejected)

    def test_escape_rejects_panel_and_stops_countdown(self) -> None:
        panel = MXBIPanel()
        countdown = find_countdown(panel)
        panel.show()
        self.application.processEvents()

        QTest.keyClick(panel, Qt.Key.Key_Escape)
        self.application.processEvents()

        self.assertEqual(panel.result(), QDialog.DialogCode.Rejected)
        self.assertFalse(countdown.is_active())

    def test_only_mxbi_panel_configures_latest_timeout(self) -> None:
        mxbi_panel = MXBIPanel()
        experiment_panel = ExperimentPanel(SceneManager())

        mxbi_labels = [label.text() for label in mxbi_panel.findChildren(QLabel)]
        experiment_labels = [
            label.text() for label in experiment_panel.findChildren(QLabel)
        ]
        self.assertIn("auto accept (s):", mxbi_labels)
        self.assertNotIn("auto accept (s)", experiment_labels)

        timeout_input = mxbi_panel.findChild(QSpinBox)
        self.assertIsNotNone(timeout_input)
        if timeout_input is None:
            raise AssertionError("Auto-accept timeout input not found in MXBI panel")
        timeout_input.setValue(17)
        QTest.mouseClick(mxbi_panel.save_button, Qt.MouseButton.LeftButton)

        experiment_panel.show()
        self.application.processEvents()
        countdown = find_countdown(experiment_panel)
        countdown_label = countdown.findChild(QLabel)
        self.assertIsNotNone(countdown_label)
        if countdown_label is None:
            raise AssertionError("Remaining-time label not found in countdown widget")
        self.assertEqual(countdown_label.text(), "Auto: 17s")

        experiment_save = next(
            button
            for button in experiment_panel.findChildren(QPushButton)
            if button.text() == "Save"
        )
        QTest.mouseClick(experiment_save, Qt.MouseButton.LeftButton)
        persisted_config = MXBIPanelConfig.model_validate_json(
            get_mxbi_panel_config_path().read_text(encoding="utf-8")
        )
        self.assertEqual(persisted_config.auto_accept_timeout_seconds, 17)

        mxbi_panel.close()
        experiment_panel.close()

    def test_zero_timeout_disables_both_countdowns(self) -> None:
        panel_config_path = get_mxbi_panel_config_path()
        panel_config_path.parent.mkdir(parents=True, exist_ok=True)
        panel_config_path.write_text(
            MXBIPanelConfig(auto_accept_timeout_seconds=0).model_dump_json(indent=4),
            encoding="utf-8",
        )

        mxbi_panel = MXBIPanel()
        experiment_panel = ExperimentPanel(SceneManager())
        mxbi_countdown = find_countdown(mxbi_panel)
        experiment_countdown = find_countdown(experiment_panel)
        mxbi_panel.show()
        experiment_panel.show()
        self.application.processEvents()

        self.assertFalse(mxbi_countdown.is_active())
        self.assertFalse(experiment_countdown.is_active())

        mxbi_panel.close()
        experiment_panel.close()


if __name__ == "__main__":
    unittest.main()
