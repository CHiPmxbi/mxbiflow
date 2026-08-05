# pyright: reportPrivateUsage=false

import os
import unittest
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymotego import (
    BackupDestination,
    BackupPhase,
    BackupSource,
    BackupStatus,
    BackupTask,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mxbiflow.infra.backup import BackupTaskRunner
from mxbiflow.ui.backup import (
    BackupPanel,
    BackupPanelTask,
    _PanelTaskStatus,
    _task_progress_percent,
    run_backup,
    run_session_backup,
)

SOURCE = BackupSource(root_id="project-data", entries=("run-01",))
DESTINATION = BackupDestination(root_id="lab-nas", path="experiments/data")


def make_task(
    status: BackupStatus,
    *,
    files_total: int = 10,
    files_completed: int = 5,
    bytes_total: int = 100,
    bytes_transferred: int = 50,
    error: str | None = None,
) -> BackupTask:
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
        created_at=datetime(2026, 7, 31, tzinfo=UTC),
        files_total=files_total,
        files_completed=files_completed,
        bytes_total=bytes_total,
        bytes_transferred=bytes_transferred,
        current_path="run-01/data.bin",
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
        self.closed = False

    def create(
        self,
        _source: BackupSource,
        _destination: BackupDestination,
    ) -> BackupTask:
        return make_task(BackupStatus.RUNNING)

    def current(self) -> BackupTask:
        if self._response_gate is not None:
            self._response_gate.wait(1)
        return self._responses.popleft()

    def close(self) -> None:
        self.closed = True


def completed_runner(
    status: BackupStatus, *, error: str | None = None
) -> BackupTaskRunner:
    client = FakeBackupClient([make_task(status, error=error)])
    runner = BackupTaskRunner(poll_interval_s=0.001)
    with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
        runner.start(SOURCE, DESTINATION)
    if not runner.wait(1):
        raise AssertionError("Backup runner did not finish")
    return runner


def panel_with_runner(
    runner: BackupTaskRunner,
    *,
    success_auto_close_ms: int,
    task: BackupPanelTask | None = None,
) -> BackupPanel:
    with (
        patch("mxbiflow.ui.backup.BackupTaskRunner", return_value=runner),
        patch.object(runner, "start"),
    ):
        return BackupPanel(
            SOURCE,
            DESTINATION,
            success_auto_close_ms=success_auto_close_ms,
            task=task,
        )


class BackupUITests(unittest.TestCase):
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
        self.assertEqual(
            _task_progress_percent(
                make_task(
                    BackupStatus.RUNNING,
                    bytes_total=0,
                    bytes_transferred=0,
                    files_total=8,
                    files_completed=2,
                )
            ),
            25,
        )
        self.assertIsNone(
            _task_progress_percent(
                make_task(
                    BackupStatus.RUNNING,
                    bytes_total=0,
                    bytes_transferred=0,
                    files_total=0,
                    files_completed=0,
                )
            )
        )

    def test_success_closes_automatically(self) -> None:
        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=0,
        )
        dialog.show()

        self.application.processEvents()
        self.application.processEvents()

        self.assertFalse(dialog.isVisible())
        self.assertEqual(dialog._progress_bar.value(), 100)

    def test_success_waits_for_background_task_and_shows_done(self) -> None:
        task_gate = Event()

        def wait_for_task_gate() -> None:
            task_gate.wait(1)

        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=5_000,
            task=BackupPanelTask(
                label="Daily report",
                action=wait_for_task_gate,
            ),
        )
        dialog.show()

        dialog._refresh()
        first_frame = dialog._task_status_label.text()
        dialog._refresh()
        second_frame = dialog._task_status_label.text()
        self.assertNotEqual(first_frame, second_frame)
        self.assertFalse(dialog._close_button.isEnabled())
        self.assertFalse(dialog._auto_close_timer.isActive())

        task_gate.set()
        assert dialog._task_runner is not None
        for _ in range(100):
            if dialog._task_runner.status is _PanelTaskStatus.SUCCEEDED:
                break
            QTest.qWait(10)
        dialog._refresh()

        self.assertEqual(dialog._task_status_label.text(), "✓ Daily report: Done")
        self.assertTrue(dialog._close_button.isEnabled())
        self.assertTrue(dialog._auto_close_timer.isActive())
        dialog.accept()

    def test_background_task_failure_is_shown_and_requires_manual_close(self) -> None:
        def fail() -> None:
            raise RuntimeError("SMTP unavailable")

        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=5_000,
            task=BackupPanelTask(label="Daily report", action=fail),
        )
        dialog.show()
        assert dialog._task_runner is not None
        for _ in range(100):
            if dialog._task_runner.status is _PanelTaskStatus.FAILED:
                break
            QTest.qWait(10)
        dialog._refresh()

        self.assertEqual(dialog._task_status_label.text(), "✕ Daily report: Failed")
        self.assertIn("SMTP unavailable", dialog._task_error_label.text())
        self.assertTrue(dialog._close_button.isEnabled())
        self.assertFalse(dialog._auto_close_timer.isActive())
        dialog.accept()

    def test_disabled_background_task_is_shown_as_skipped(self) -> None:
        action = Mock()
        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=5_000,
            task=BackupPanelTask(
                label="Daily report",
                action=action,
                enabled=False,
            ),
        )
        dialog.show()
        dialog._refresh()

        action.assert_not_called()
        self.assertEqual(dialog._task_status_label.text(), "Daily report: Skipped")
        self.assertTrue(dialog._close_button.isEnabled())
        dialog.accept()

    def test_success_shows_auto_close_countdown(self) -> None:
        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=5_000,
        )
        dialog.show()
        self.application.processEvents()

        self.assertTrue(dialog._countdown_label.isVisible())
        self.assertEqual(dialog._countdown_label.text(), "Auto-closing in 5s")
        self.assertTrue(dialog._stop_countdown_button.isEnabled())
        self.assertTrue(dialog._close_button.isEnabled())

        dialog._tick_countdown()
        self.assertEqual(dialog._countdown_label.text(), "Auto-closing in 4s")
        dialog.accept()

    def test_only_stop_button_stops_auto_close_countdown(self) -> None:
        dialog = panel_with_runner(
            completed_runner(BackupStatus.SUCCEEDED),
            success_auto_close_ms=5_000,
        )
        dialog.show()
        self.application.processEvents()

        QTest.mouseClick(dialog, Qt.MouseButton.LeftButton)
        self.application.processEvents()

        self.assertTrue(dialog._countdown_timer.isActive())
        self.assertTrue(dialog._auto_close_timer.isActive())

        countdown_text = dialog._countdown_label.text()
        QTest.mouseClick(
            dialog._stop_countdown_button,
            Qt.MouseButton.LeftButton,
        )
        self.application.processEvents()

        self.assertFalse(dialog._countdown_timer.isActive())
        self.assertFalse(dialog._auto_close_timer.isActive())
        self.assertEqual(dialog._countdown_label.text(), countdown_text)
        self.assertFalse(dialog._stop_countdown_button.isEnabled())
        self.assertTrue(dialog._close_button.isEnabled())

        self.application.processEvents()
        self.application.processEvents()
        self.assertTrue(dialog.isVisible())
        dialog.accept()

    def test_failure_and_partial_success_require_manual_close(self) -> None:
        for status in (
            BackupStatus.FAILED,
            BackupStatus.PARTIALLY_SUCCEEDED,
        ):
            with self.subTest(status=status):
                dialog = panel_with_runner(
                    completed_runner(status, error="entry failed"),
                    success_auto_close_ms=5_000,
                )
                dialog.show()
                self.application.processEvents()

                self.assertTrue(dialog.isVisible())
                self.assertFalse(dialog._countdown_timer.isActive())
                self.assertFalse(dialog._auto_close_timer.isActive())
                self.assertFalse(dialog._stop_countdown_button.isEnabled())
                self.assertTrue(dialog._close_button.isEnabled())
                self.assertIn("entry failed", dialog._error_label.text())
                dialog.accept()

    def test_close_is_ignored_while_backup_is_running(self) -> None:
        response_gate = Event()
        client = FakeBackupClient(
            [make_task(BackupStatus.SUCCEEDED)],
            response_gate=response_gate,
        )
        runner = BackupTaskRunner(poll_interval_s=0.001)
        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            runner.start(SOURCE, DESTINATION)

        dialog = panel_with_runner(runner, success_auto_close_ms=0)
        dialog.show()
        self.application.processEvents()
        self.assertTrue(dialog._stop_countdown_button.isVisible())
        self.assertFalse(dialog._stop_countdown_button.isEnabled())
        self.assertTrue(dialog._close_button.isVisible())
        self.assertFalse(dialog._close_button.isEnabled())
        dialog.close()
        self.application.processEvents()

        self.assertTrue(dialog.isVisible())

        response_gate.set()
        self.assertTrue(runner.wait(1))
        dialog._refresh()
        self.application.processEvents()
        self.assertFalse(dialog.isVisible())

    def test_run_backup_creates_and_shows_backup(self) -> None:
        client = FakeBackupClient([make_task(BackupStatus.SUCCEEDED)])

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            run_backup(
                SOURCE,
                DESTINATION,
                poll_interval_s=0.001,
                success_auto_close_ms=0,
            )

        self.assertTrue(client.closed)

    @patch("mxbiflow.ui.backup.run_backup")
    def test_session_backup_uses_configured_roots_and_participant_paths(
        self,
        run_backup_mock: Mock,
    ) -> None:
        session = Mock()
        session.participant_data_paths = (
            Path("animal-1/20260805/1"),
            Path("animal-2/20260805/1"),
        )
        session.mxbi_config = SimpleNamespace(
            backup_source_root_id="mxbi-data",
            backup_destination_root_id="mxbi-server",
        )

        run_session_backup(session)

        source, destination = run_backup_mock.call_args.args
        self.assertEqual(source.root_id, "mxbi-data")
        self.assertEqual(
            source.entries,
            (
                "animal-1/20260805/1",
                "animal-2/20260805/1",
            ),
        )
        self.assertEqual(destination.root_id, "mxbi-server")

    @patch("mxbiflow.ui.backup.run_backup")
    def test_session_backup_rejects_session_without_data(
        self,
        run_backup_mock: Mock,
    ) -> None:
        session = Mock()
        session.participant_data_paths = ()

        with self.assertRaisesRegex(RuntimeError, "no data"):
            run_session_backup(session)

        run_backup_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
