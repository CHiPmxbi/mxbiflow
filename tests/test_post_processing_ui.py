# pyright: reportPrivateUsage=false

import os
import unittest
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymotego import (
    BackupDestination,
    BackupPhase,
    BackupSource,
    BackupStatus,
    BackupTask,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mxbiflow.infra.backup import BackupTaskRunner
from mxbiflow.ui.post_processing_panel import (
    PostProcessingPanel,
    _StepStatus,
    _task_progress_percent,
    run_session_post_processing,
)

SOURCE = BackupSource(root_id="source", entries=("run",))
DESTINATION = BackupDestination(root_id="destination")


def make_task(status: BackupStatus, *, error: str | None = None) -> BackupTask:
    return BackupTask(
        id="task-123",
        status=status,
        phase=(
            BackupPhase.COMPLETED
            if status is not BackupStatus.RUNNING
            else BackupPhase.UPLOADING
        ),
        source=SOURCE,
        destination=DESTINATION,
        entries=(),
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        files_total=10,
        files_completed=5,
        bytes_total=100,
        bytes_transferred=50,
        current_path="run/data.bin",
        error=error,
    )


class FakeBackupClient:
    def __init__(
        self,
        responses: Iterable[BackupTask],
        *,
        response_gate: Event | None = None,
    ) -> None:
        self._responses = deque(responses)
        self._response_gate = response_gate

    def create(self, _source: object, _destination: object) -> BackupTask:
        return make_task(BackupStatus.RUNNING)

    def current(self) -> BackupTask:
        if self._response_gate is not None:
            self._response_gate.wait(1)
        return self._responses.popleft()

    def close(self) -> None:
        pass


def completed_runner(
    status: BackupStatus, *, error: str | None = None
) -> BackupTaskRunner:
    runner = BackupTaskRunner(poll_interval_s=0.001)
    with patch(
        "mxbiflow.infra.backup.BackupClient",
        return_value=FakeBackupClient([make_task(status, error=error)]),
    ):
        runner.start(SOURCE, DESTINATION)
    if not runner.wait(1):
        raise AssertionError("Backup runner did not finish")
    return runner


def make_session(*, sync_data: bool = True, send_email: bool = True) -> Mock:
    session = Mock()
    session.sync_data = sync_data
    session.send_email = send_email
    session.participant_data_paths = [Path("m1/20260805/1")]
    session.mxbi_config.backup_source_root_id = "source"
    session.mxbi_config.backup_destination_root_id = "destination"
    return session


def make_panel(
    session: Mock,
    runner: BackupTaskRunner,
    *,
    success_auto_close_ms: int = 5_000,
) -> PostProcessingPanel:
    with (
        patch(
            "mxbiflow.ui.post_processing_panel.BackupTaskRunner",
            return_value=runner,
        ),
        patch.object(runner, "start"),
    ):
        return PostProcessingPanel(
            session,
            {},
            success_auto_close_ms=success_auto_close_ms,
        )


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

    def test_progress_prefers_bytes_then_files(self) -> None:
        self.assertEqual(_task_progress_percent(make_task(BackupStatus.RUNNING)), 50)

    @patch("mxbiflow.ui.post_processing_panel.send_session_report")
    def test_report_starts_only_after_backup_finishes(self, send_report: Mock) -> None:
        gate = Event()
        runner = BackupTaskRunner(poll_interval_s=0.001)
        with patch(
            "mxbiflow.infra.backup.BackupClient",
            return_value=FakeBackupClient(
                [make_task(BackupStatus.SUCCEEDED)], response_gate=gate
            ),
        ):
            runner.start(SOURCE, DESTINATION)
        dialog = make_panel(make_session(), runner)
        dialog.show()

        dialog._refresh()
        send_report.assert_not_called()
        self.assertEqual(dialog._report_runner.status, _StepStatus.PENDING)

        gate.set()
        self.assertTrue(runner.wait(1))
        dialog._refresh()
        for _ in range(100):
            if dialog._report_runner.status is _StepStatus.SUCCEEDED:
                break
            QTest.qWait(10)

        send_report.assert_called_once()
        dialog.accept()

    @patch("mxbiflow.ui.post_processing_panel.send_session_report")
    def test_backup_failure_still_runs_report(self, send_report: Mock) -> None:
        dialog = make_panel(
            make_session(),
            completed_runner(BackupStatus.FAILED, error="backup failed"),
        )
        dialog.show()
        dialog._refresh()
        for _ in range(100):
            if dialog._report_runner.status is _StepStatus.SUCCEEDED:
                break
            QTest.qWait(10)
        dialog._refresh()

        send_report.assert_called_once()
        self.assertIn("backup failed", dialog._error_label.text())
        self.assertTrue(dialog._close_button.isEnabled())
        self.assertFalse(dialog._auto_close_timer.isActive())
        dialog.accept()

    @patch("mxbiflow.ui.post_processing_panel.send_session_report")
    def test_configuration_flags_show_skipped_steps(self, send_report: Mock) -> None:
        dialog = make_panel(
            make_session(sync_data=False, send_email=False),
            BackupTaskRunner(),
            success_auto_close_ms=5_000,
        )
        dialog.show()
        dialog._refresh()

        send_report.assert_not_called()
        self.assertEqual(dialog._backup_status_label.text(), "Backup: Skipped")
        self.assertEqual(dialog._report_status_label.text(), "Daily report: Skipped")
        self.assertTrue(dialog._auto_close_timer.isActive())
        dialog.accept()

    @patch(
        "mxbiflow.ui.post_processing_panel.send_session_report",
        side_effect=RuntimeError("SMTP unavailable"),
    )
    def test_report_failure_requires_manual_close(self, _send_report: Mock) -> None:
        dialog = make_panel(
            make_session(sync_data=False),
            BackupTaskRunner(),
        )
        dialog.show()
        for _ in range(100):
            if dialog._report_runner.status is _StepStatus.FAILED:
                break
            QTest.qWait(10)
        dialog._refresh()

        self.assertIn("SMTP unavailable", dialog._error_label.text())
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
