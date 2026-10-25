# pyright: reportPrivateUsage=false

import os
import unittest
from threading import Event
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mxbiflow.ui.post_processing_panel import (
    PostProcessingPanel,
    _StepStatus,
    run_session_post_processing,
)


def make_session(*, send_email: bool = True) -> Mock:
    session = Mock()
    session.send_email = send_email
    return session


def wait_for(dialog: PostProcessingPanel, status: _StepStatus) -> None:
    for _ in range(100):
        if dialog._report_runner.status is status:
            break
        QTest.qWait(10)
    dialog._refresh()


class PostProcessingUITests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def tearDown(self) -> None:
        for widget in self.application.topLevelWidgets():
            widget.close()
        self.application.processEvents()

    @patch("mxbiflow.ui.post_processing_panel.send_session_report")
    def test_report_success_auto_closes(self, send_report: Mock) -> None:
        gate = Event()
        send_report.side_effect = lambda *_: gate.wait(1)
        dialog = PostProcessingPanel(make_session(), {}, success_auto_close_ms=5_000)
        dialog.show()

        dialog._refresh()
        self.assertFalse(dialog._close_button.isEnabled())

        gate.set()
        wait_for(dialog, _StepStatus.SUCCEEDED)

        send_report.assert_called_once()
        self.assertEqual(dialog._report_status_label.text(), "✓ Daily report: Done")
        self.assertTrue(dialog._auto_close_timer.isActive())
        dialog.accept()

    @patch("mxbiflow.ui.post_processing_panel.send_session_report")
    def test_disabled_report_is_skipped(self, send_report: Mock) -> None:
        dialog = PostProcessingPanel(
            make_session(send_email=False), {}, success_auto_close_ms=5_000
        )
        dialog.show()
        dialog._refresh()

        send_report.assert_not_called()
        self.assertEqual(dialog._report_status_label.text(), "Daily report: Skipped")
        self.assertTrue(dialog._auto_close_timer.isActive())
        dialog.accept()

    @patch(
        "mxbiflow.ui.post_processing_panel.send_session_report",
        side_effect=RuntimeError("cogmote unavailable"),
    )
    def test_report_failure_requires_manual_close(self, _send_report: Mock) -> None:
        dialog = PostProcessingPanel(make_session(), {})
        dialog.show()
        wait_for(dialog, _StepStatus.FAILED)

        self.assertIn("cogmote unavailable", dialog._error_label.text())
        self.assertTrue(dialog._close_button.isEnabled())
        self.assertFalse(dialog._auto_close_timer.isActive())
        dialog.accept()

    @patch("mxbiflow.ui.post_processing_panel.PostProcessingPanel")
    @patch("mxbiflow.ui.post_processing_panel.require_application")
    def test_entrypoint_opens_panel(
        self,
        require_application: Mock,
        panel_cls: Mock,
    ) -> None:
        session = make_session()
        processors = {"stage": Mock()}

        run_session_post_processing(session, processors)

        require_application.assert_called_once_with()
        panel_cls.assert_called_once_with(session, processors)
        panel_cls.return_value.exec.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
