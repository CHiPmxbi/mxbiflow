import unittest
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from unittest.mock import patch

from httpx import ConnectError
from pymotego import (
    BackupDestination,
    BackupPhase,
    BackupSource,
    BackupStatus,
    BackupTask,
)

from mxbiflow.infra.backup import BackupMonitoringError, BackupTaskRunner

SOURCE = BackupSource(root_id="project-data", entries=("run-01",))
DESTINATION = BackupDestination(root_id="lab-nas", path="experiments/data")


def make_task(
    status: BackupStatus,
    *,
    task_id: str = "task-123",
) -> BackupTask:
    return BackupTask(
        id=task_id,
        status=status,
        phase=(
            BackupPhase.COMPLETED
            if status is not BackupStatus.RUNNING
            else BackupPhase.UPLOADING
        ),
        source=SOURCE,
        destination=DESTINATION,
        entries=(),
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        files_total=10,
        files_completed=10 if status is not BackupStatus.RUNNING else 5,
        bytes_total=100,
        bytes_transferred=100 if status is not BackupStatus.RUNNING else 50,
    )


class FakeBackupClient:
    def __init__(
        self,
        responses: Iterable[BackupTask | None | Exception],
        *,
        create_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.responses = deque(responses)
        self.create_error = create_error
        self.close_error = close_error
        self.create_calls: list[tuple[BackupSource, BackupDestination]] = []
        self.closed = False

    def create(
        self,
        source: BackupSource,
        destination: BackupDestination,
    ) -> BackupTask:
        self.create_calls.append((source, destination))
        if self.create_error is not None:
            raise self.create_error
        return make_task(BackupStatus.RUNNING)

    def current(self) -> BackupTask | None:
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class BackupTaskRunnerTests(unittest.TestCase):
    def test_monitors_created_task_until_success(self) -> None:
        final_task = make_task(BackupStatus.SUCCEEDED)
        client = FakeBackupClient([make_task(BackupStatus.RUNNING), final_task])
        monitor = BackupTaskRunner(poll_interval_s=0.001)

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            created = monitor.start(SOURCE, DESTINATION)

        self.assertEqual(client.create_calls, [(SOURCE, DESTINATION)])
        self.assertEqual(created.status, BackupStatus.RUNNING)
        self.assertTrue(monitor.wait(1))
        self.assertEqual(monitor.latest_task, final_task)
        self.assertIsNone(monitor.error)
        self.assertFalse(monitor.is_monitoring)
        self.assertTrue(client.closed)

    def test_all_terminal_statuses_stop_monitoring(self) -> None:
        for status in (
            BackupStatus.SUCCEEDED,
            BackupStatus.PARTIALLY_SUCCEEDED,
            BackupStatus.FAILED,
        ):
            with self.subTest(status=status):
                client = FakeBackupClient([make_task(status)])
                monitor = BackupTaskRunner(poll_interval_s=0.001)

                with patch(
                    "mxbiflow.infra.backup.BackupClient",
                    return_value=client,
                ):
                    monitor.start(SOURCE, DESTINATION)

                self.assertTrue(monitor.wait(1))
                task = monitor.latest_task
                self.assertIsNotNone(task)
                assert task is not None
                self.assertIs(task.status, status)

    def test_successful_poll_starts_a_new_retry_cycle(self) -> None:
        final_task = make_task(BackupStatus.SUCCEEDED)
        client = FakeBackupClient(
            [
                ConnectError("temporary one"),
                ConnectError("temporary two"),
                make_task(BackupStatus.RUNNING),
                ConnectError("temporary three"),
                ConnectError("temporary four"),
                final_task,
            ]
        )
        monitor = BackupTaskRunner(
            poll_interval_s=0.001,
            max_attempts=3,
        )

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            monitor.start(SOURCE, DESTINATION)

        self.assertTrue(monitor.wait(1))
        self.assertEqual(monitor.latest_task, final_task)
        self.assertIsNone(monitor.error)

    def test_stores_last_original_error_when_retries_are_exhausted(self) -> None:
        errors = [
            ConnectError("one"),
            ConnectError("two"),
            ConnectError("three"),
        ]
        client = FakeBackupClient(errors)
        monitor = BackupTaskRunner(
            poll_interval_s=0.001,
            max_attempts=3,
        )

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            monitor.start(SOURCE, DESTINATION)

        self.assertTrue(monitor.wait(1))
        self.assertIs(monitor.error, errors[-1])
        self.assertTrue(client.closed)

    def test_none_and_mismatched_task_are_retried(self) -> None:
        client = FakeBackupClient(
            [
                None,
                make_task(BackupStatus.RUNNING, task_id="another-task"),
            ]
        )
        monitor = BackupTaskRunner(
            poll_interval_s=0.001,
            max_attempts=2,
        )

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            monitor.start(SOURCE, DESTINATION)

        self.assertTrue(monitor.wait(1))
        self.assertIsInstance(monitor.error, BackupMonitoringError)
        assert monitor.error is not None
        self.assertIn("another-task", str(monitor.error))

    def test_create_failure_can_be_retried(self) -> None:
        create_error = RuntimeError("create failed")
        failed_client = FakeBackupClient(
            [],
            create_error=create_error,
            close_error=ConnectError("close failed"),
        )
        successful_client = FakeBackupClient([make_task(BackupStatus.SUCCEEDED)])
        monitor = BackupTaskRunner(poll_interval_s=0.001)

        with patch(
            "mxbiflow.infra.backup.BackupClient",
            side_effect=[failed_client, successful_client],
        ):
            with self.assertRaises(RuntimeError) as raised:
                monitor.start(SOURCE, DESTINATION)

            self.assertIs(raised.exception, create_error)
            self.assertFalse(monitor.is_monitoring)
            self.assertTrue(monitor.wait(0))
            self.assertTrue(failed_client.closed)

            monitor.start(SOURCE, DESTINATION)

        self.assertTrue(monitor.wait(1))
        self.assertTrue(successful_client.closed)

    def test_rejects_second_start_after_successful_creation(self) -> None:
        client = FakeBackupClient(
            [make_task(BackupStatus.RUNNING), make_task(BackupStatus.SUCCEEDED)]
        )
        monitor = BackupTaskRunner(poll_interval_s=0.1)

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            monitor.start(SOURCE, DESTINATION)
            with self.assertRaisesRegex(RuntimeError, "already"):
                monitor.start(SOURCE, DESTINATION)

        self.assertTrue(monitor.wait(1))
        with self.assertRaisesRegex(RuntimeError, "already"):
            monitor.start(SOURCE, DESTINATION)

    def test_wait_times_out_while_monitoring(self) -> None:
        client = FakeBackupClient(
            [make_task(BackupStatus.RUNNING), make_task(BackupStatus.SUCCEEDED)]
        )
        monitor = BackupTaskRunner(poll_interval_s=0.1)

        with patch("mxbiflow.infra.backup.BackupClient", return_value=client):
            monitor.start(SOURCE, DESTINATION)

        self.assertFalse(monitor.wait(0.001))
        self.assertTrue(monitor.wait(1))

    def test_validates_monitor_configuration(self) -> None:
        with self.assertRaises(ValueError):
            BackupTaskRunner(poll_interval_s=0)
        with self.assertRaises(ValueError):
            BackupTaskRunner(max_attempts=0)


if __name__ == "__main__":
    unittest.main()
