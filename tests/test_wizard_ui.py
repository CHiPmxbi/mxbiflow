import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from mxbiflow.ui.application import require_application
from mxbiflow.ui.wizard import run_wizard


class ApplicationTests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def test_existing_application_is_reused_and_kept_running(self) -> None:
        self.application.setQuitOnLastWindowClosed(True)

        result = require_application()

        self.assertIs(result, self.application)
        self.assertFalse(result.quitOnLastWindowClosed())


class WizardTests(unittest.TestCase):
    @patch("mxbiflow.ui.wizard.ExperimentPanel")
    @patch("mxbiflow.ui.wizard.MXBIPanel")
    @patch("mxbiflow.ui.wizard.require_application")
    def test_first_panel_rejection_stops_the_wizard(
        self,
        require_application: Mock,
        mxbi_panel_class: Mock,
        experiment_panel_class: Mock,
    ) -> None:
        mxbi_panel_class.return_value.exec.return_value = QDialog.DialogCode.Rejected

        self.assertFalse(run_wizard(Mock()))

        require_application.assert_called_once_with()
        experiment_panel_class.assert_not_called()

    @patch("mxbiflow.ui.wizard.ExperimentPanel")
    @patch("mxbiflow.ui.wizard.MXBIPanel")
    @patch("mxbiflow.ui.wizard.require_application")
    def test_second_panel_rejection_returns_false(
        self,
        _require_application: Mock,
        mxbi_panel_class: Mock,
        experiment_panel_class: Mock,
    ) -> None:
        mxbi_panel_class.return_value.exec.return_value = QDialog.DialogCode.Accepted
        experiment_panel_class.return_value.exec.return_value = (
            QDialog.DialogCode.Rejected
        )

        self.assertFalse(run_wizard(Mock()))

    @patch("mxbiflow.ui.wizard.ExperimentPanel")
    @patch("mxbiflow.ui.wizard.MXBIPanel")
    @patch("mxbiflow.ui.wizard.require_application")
    def test_accepted_panels_run_in_order(
        self,
        _require_application: Mock,
        mxbi_panel_class: Mock,
        experiment_panel_class: Mock,
    ) -> None:
        events: list[str] = []
        mxbi_panel_class.return_value.exec.side_effect = lambda: (
            events.append("mxbi") or QDialog.DialogCode.Accepted
        )
        experiment_panel_class.return_value.exec.side_effect = lambda: (
            events.append("experiment") or QDialog.DialogCode.Accepted
        )

        self.assertTrue(run_wizard(Mock()))
        self.assertEqual(events, ["mxbi", "experiment"])

    def test_application_is_created_and_kept_available(self) -> None:
        code = """
import os
import gc
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from mxbiflow.ui.application import require_application

application = require_application()
assert QApplication.instance() is application
assert not application.quitOnLastWindowClosed()
del application
gc.collect()
assert isinstance(QApplication.instance(), QApplication)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
