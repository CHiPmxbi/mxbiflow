from threading import Lock, Thread
from time import sleep

import stamina
from httpx import HTTPError
from pymotego import (
    BackupClient,
    BackupDestination,
    BackupError,
    BackupSource,
    BackupStatus,
    BackupTask,
)


class BackupMonitoringError(RuntimeError):
    """Raised when a created backup task cannot be monitored."""


_TERMINAL_STATUSES = frozenset(
    {
        BackupStatus.SUCCEEDED,
        BackupStatus.PARTIALLY_SUCCEEDED,
        BackupStatus.FAILED,
    }
)
_RETRYABLE_ERRORS = (BackupError, HTTPError, BackupMonitoringError)


class BackupTaskRunner:
    """Create and monitor one backup task in a background thread."""

    def __init__(
        self,
        *,
        poll_interval_s: float = 1.0,
        max_attempts: int = 3,
    ) -> None:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be greater than zero")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")

        self._poll_interval_s = poll_interval_s
        self._max_attempts = max_attempts
        self._lock = Lock()
        self._thread: Thread | None = None
        self._starting = False
        self._is_monitoring = False
        self._has_created_task = False
        self._latest_task: BackupTask | None = None
        self._error: Exception | None = None

    @property
    def latest_task(self) -> BackupTask | None:
        with self._lock:
            return self._latest_task

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    @property
    def is_monitoring(self) -> bool:
        with self._lock:
            return self._starting or self._is_monitoring

    def start(
        self,
        source: BackupSource,
        destination: BackupDestination,
    ) -> BackupTask:
        """Create a backup synchronously, then monitor it in a daemon thread."""
        with self._lock:
            if self._starting or self._has_created_task:
                raise RuntimeError(
                    "This BackupTaskRunner has already created a backup task"
                )
            self._starting = True

        client = BackupClient()
        try:
            created_task = client.create(source, destination)
        except Exception:
            _close_preserving_active_exception(client)
            with self._lock:
                self._starting = False
            raise

        thread = Thread(
            target=self._monitor,
            args=(client, created_task.id),
            name=f"backup-monitor-{created_task.id}",
            daemon=True,
        )
        with self._lock:
            self._has_created_task = True
            self._latest_task = created_task
            self._error = None
            self._thread = thread
            self._starting = False
            self._is_monitoring = True

        try:
            thread.start()
        except Exception as error:
            _close_preserving_active_exception(client)
            with self._lock:
                self._error = error
                self._is_monitoring = False
            raise

        return created_task

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for monitoring to finish and return whether it has stopped."""
        with self._lock:
            thread = self._thread
            starting = self._starting

        if thread is None:
            return not starting

        thread.join(timeout)
        return not thread.is_alive()

    def _monitor(self, client: BackupClient, task_id: str) -> None:
        retryer = stamina.RetryingCaller(
            attempts=self._max_attempts,
            timeout=None,
            wait_initial=self._poll_interval_s,
            wait_max=self._poll_interval_s,
            wait_jitter=0,
            wait_exp_base=1,
        )
        try:
            while True:
                try:
                    task = retryer(
                        _RETRYABLE_ERRORS,
                        _get_current_task,
                        client,
                        task_id,
                    )
                except _RETRYABLE_ERRORS as error:
                    with self._lock:
                        self._error = error
                    return

                with self._lock:
                    self._latest_task = task
                if task.status in _TERMINAL_STATUSES:
                    return

                sleep(self._poll_interval_s)
        finally:
            try:
                client.close()
            except _RETRYABLE_ERRORS as error:
                with self._lock:
                    if self._error is None:
                        self._error = error
            finally:
                with self._lock:
                    self._is_monitoring = False


def _get_current_task(client: BackupClient, task_id: str) -> BackupTask:
    task = client.current()
    if task is None:
        raise BackupMonitoringError(f"Backup task {task_id!r} was not found")
    if task.id != task_id:
        raise BackupMonitoringError(
            f"Expected backup task {task_id!r}, got {task.id!r}"
        )
    return task


def _close_preserving_active_exception(client: BackupClient) -> None:
    """Close a client without replacing an exception already being handled."""
    try:
        client.close()
    except _RETRYABLE_ERRORS:
        pass
