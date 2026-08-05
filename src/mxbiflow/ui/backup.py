from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, auto
from threading import Lock, Thread

from pymotego import (
    BackupDestination,
    BackupSource,
    BackupStatus,
    BackupTask,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..infra.backup import BackupTaskRunner
from ..models.session import Session
from .application import require_application

_REFRESH_INTERVAL_MS = 250
_SUCCESS_AUTO_CLOSE_MS = 10_000
_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")


@dataclass(frozen=True)
class BackupPanelTask:
    label: str
    action: Callable[[], None]
    enabled: bool = True


class _PanelTaskStatus(StrEnum):
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    SKIPPED = auto()


class _PanelTaskRunner:
    def __init__(self, task: BackupPanelTask) -> None:
        self.task = task
        self._lock = Lock()
        self._status = (
            _PanelTaskStatus.RUNNING if task.enabled else _PanelTaskStatus.SKIPPED
        )
        self._error: Exception | None = None

    @property
    def status(self) -> _PanelTaskStatus:
        with self._lock:
            return self._status

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    def start(self) -> None:
        if not self.task.enabled:
            return
        Thread(
            target=self._run,
            name="backup-panel-task",
            daemon=True,
        ).start()

    def _run(self) -> None:
        try:
            self.task.action()
        except Exception as error:  # noqa: BLE001 - task failures are shown in the panel
            with self._lock:
                self._error = error
                self._status = _PanelTaskStatus.FAILED
        else:
            with self._lock:
                self._status = _PanelTaskStatus.SUCCEEDED


def run_backup(
    source: BackupSource,
    destination: BackupDestination,
    *,
    poll_interval_s: float = 1.0,
    max_attempts: int = 3,
    refresh_interval_ms: int = _REFRESH_INTERVAL_MS,
    success_auto_close_ms: int = _SUCCESS_AUTO_CLOSE_MS,
    task: BackupPanelTask | None = None,
) -> None:
    """Create a backup and show a blocking progress dialog."""
    _application = require_application()
    BackupPanel(
        source,
        destination,
        poll_interval_s=poll_interval_s,
        max_attempts=max_attempts,
        refresh_interval_ms=refresh_interval_ms,
        success_auto_close_ms=success_auto_close_ms,
        task=task,
    ).exec()


def run_session_backup(session: Session) -> None:
    """Back up all data produced by a completed session."""
    entries = list(session.participant_data_paths)
    if not entries:
        raise RuntimeError("Session has no data available for backup")

    run_backup(
        BackupSource(
            root_id=session.mxbi_config.backup_source_root_id,
            entries=tuple(path.as_posix() for path in entries),
        ),
        BackupDestination(
            root_id=session.mxbi_config.backup_destination_root_id,
        ),
    )


class BackupPanel(QDialog):
    def __init__(
        self,
        source: BackupSource,
        destination: BackupDestination,
        *,
        poll_interval_s: float = 1.0,
        max_attempts: int = 3,
        refresh_interval_ms: int = _REFRESH_INTERVAL_MS,
        success_auto_close_ms: int = _SUCCESS_AUTO_CLOSE_MS,
        task: BackupPanelTask | None = None,
    ) -> None:
        super().__init__()
        self._runner = BackupTaskRunner(
            poll_interval_s=poll_interval_s,
            max_attempts=max_attempts,
        )
        self._runner.start(source, destination)
        self._task_runner = _PanelTaskRunner(task) if task is not None else None
        if self._task_runner is not None:
            self._task_runner.start()
        self._can_close = False
        self._terminal_state_shown = False
        self._success_auto_close_ms = success_auto_close_ms
        self._remaining_seconds = 0
        self._spinner_index = 0

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(refresh_interval_ms)
        self._refresh_timer.timeout.connect(self._refresh)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.accept)

        self._refresh()
        self._refresh_timer.start()

    def _build_ui(self) -> None:
        self.setWindowTitle("Backup Progress")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.resize(560, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self._status_label = QLabel("Backup in progress", self)
        font = self._status_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self._status_label.setFont(font)
        layout.addWidget(self._status_label)

        self._countdown_label = QLabel("", self)
        self._countdown_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self._countdown_label.hide()
        layout.addWidget(self._countdown_label)

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setAccessibleName("Backup progress")
        layout.addWidget(self._progress_bar)

        self._details_label = QLabel("", self)
        self._details_label.setWordWrap(True)
        layout.addWidget(self._details_label)

        self._path_label = QLabel("", self)
        self._path_label.setWordWrap(True)
        self._path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._path_label)

        self._task_status_label = QLabel("", self)
        self._task_status_label.setAccessibleName("Background task status")
        self._task_error_label = QLabel("", self)
        self._task_error_label.setWordWrap(True)
        self._task_error_label.setStyleSheet("color: #C62828;")
        self._task_error_label.hide()
        if self._task_runner is None:
            self._task_status_label.hide()
        layout.addWidget(self._task_status_label)
        layout.addWidget(self._task_error_label)

        self._error_label = QLabel("", self)
        self._error_label.setWordWrap(True)
        self._error_label.setAccessibleName("Backup error")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._stop_countdown_button = QPushButton("Stop countdown", self)
        self._stop_countdown_button.setEnabled(False)
        self._stop_countdown_button.clicked.connect(self._stop_auto_close)
        buttons.addWidget(self._stop_countdown_button)
        self._close_button = QPushButton("Close", self)
        self._close_button.setEnabled(False)
        self._close_button.clicked.connect(self.accept)
        buttons.addWidget(self._close_button)
        layout.addLayout(buttons)

    def _refresh(self) -> None:
        task = self._runner.latest_task
        if task is None:
            return

        self._update_progress(task)
        self._update_details(task)

        backup_done = False
        backup_error: str | None = None
        if task.status is BackupStatus.SUCCEEDED:
            backup_done = True
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(100)
            self._status_label.setText("Backup succeeded. Waiting for other tasks.")
        elif task.status in {
            BackupStatus.PARTIALLY_SUCCEEDED,
            BackupStatus.FAILED,
        }:
            backup_done = True
            backup_error = _task_failure_message(task)
            self._status_label.setText("Backup requires attention")
        elif not self._runner.is_monitoring:
            error = self._runner.error
            backup_done = True
            backup_error = (
                str(error)
                if error is not None
                else "Backup monitoring stopped before the task completed."
            )
            self._status_label.setText("Backup requires attention")

        panel_task_done, panel_task_error = self._update_panel_task()
        if self._terminal_state_shown or not backup_done or not panel_task_done:
            return

        errors = [error for error in (backup_error, panel_task_error) if error]
        if errors:
            self._show_failure("\n".join(errors))
        else:
            self._show_success()

    def _update_panel_task(self) -> tuple[bool, str | None]:
        runner = self._task_runner
        if runner is None:
            return True, None

        label = runner.task.label
        match runner.status:
            case _PanelTaskStatus.RUNNING:
                frame = _SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)]
                self._spinner_index += 1
                self._task_status_label.setStyleSheet("")
                self._task_status_label.setText(f"{frame} {label}: In progress")
                return False, None
            case _PanelTaskStatus.SUCCEEDED:
                self._task_status_label.setStyleSheet(
                    "color: #2E7D32; font-weight: bold;"
                )
                self._task_status_label.setText(f"✓ {label}: Done")
                return True, None
            case _PanelTaskStatus.SKIPPED:
                self._task_status_label.setStyleSheet("color: #666666;")
                self._task_status_label.setText(f"{label}: Skipped")
                return True, None
            case _PanelTaskStatus.FAILED:
                error = runner.error
                message = str(error) if error is not None else f"{label} failed."
                self._task_status_label.setStyleSheet(
                    "color: #C62828; font-weight: bold;"
                )
                self._task_status_label.setText(f"✕ {label}: Failed")
                self._task_error_label.setText(message)
                self._task_error_label.show()
                return True, message

    def _update_progress(self, task: BackupTask) -> None:
        progress = _task_progress_percent(task)
        if progress is None:
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setAccessibleDescription(
                "Backup progress is not available yet"
            )
            return

        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(progress)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setAccessibleDescription(
            f"Backup is {progress} percent complete"
        )

    def _update_details(self, task: BackupTask) -> None:
        phase = task.phase.value.replace("_", " ").title()
        self._details_label.setText(
            f"Phase: {phase} · "
            f"Files: {task.files_completed}/{task.files_total} · "
            f"Transferred: {_format_bytes(task.bytes_transferred)}"
            f"/{_format_bytes(task.bytes_total)}"
        )
        self._path_label.setText(
            f"Current item: {task.current_path}"
            if task.current_path
            else "Current item: —"
        )

    def _show_success(self) -> None:
        self._terminal_state_shown = True
        self._can_close = True
        self._refresh_timer.stop()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)
        self._status_label.setText("Backup succeeded.")
        self._stop_countdown_button.setEnabled(True)
        self._close_button.setEnabled(True)
        if self._success_auto_close_ms > 0:
            self._start_countdown()
        self._auto_close_timer.start(self._success_auto_close_ms)

    def _start_countdown(self) -> None:
        self._remaining_seconds = max(
            1,
            round(self._success_auto_close_ms / 1000),
        )
        self._countdown_label.show()
        self._update_countdown_label()
        self._countdown_timer.start()

    def _tick_countdown(self) -> None:
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._countdown_timer.stop()
            self._countdown_label.hide()
            return
        self._update_countdown_label()

    def _update_countdown_label(self) -> None:
        self._countdown_label.setText(f"Auto-closing in {self._remaining_seconds}s")

    def _stop_auto_close(self) -> None:
        if (
            not self._countdown_timer.isActive()
            and not self._auto_close_timer.isActive()
        ):
            return
        self._countdown_timer.stop()
        self._auto_close_timer.stop()
        self._stop_countdown_button.setEnabled(False)
        self._close_button.setFocus()

    def _show_failure(self, message: str) -> None:
        self._terminal_state_shown = True
        self._can_close = True
        self._refresh_timer.stop()
        self._auto_close_timer.stop()
        self._status_label.setText("Backup requires attention")
        self._error_label.setText(message)
        self._error_label.show()
        self._close_button.setEnabled(True)
        self._close_button.setFocus()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._can_close:
            event.ignore()
            return
        super().closeEvent(event)


def _task_progress_percent(task: BackupTask) -> int | None:
    if task.status is BackupStatus.SUCCEEDED:
        return 100
    if task.bytes_total > 0:
        return _percent(task.bytes_transferred, task.bytes_total)
    if task.files_total > 0:
        return _percent(task.files_completed, task.files_total)
    return None


def _percent(completed: int, total: int) -> int:
    return min(max(round(completed * 100 / total), 0), 100)


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(amount) < 1024 or unit == "TiB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def _task_failure_message(task: BackupTask) -> str:
    if task.error:
        return task.error

    entry_errors = [
        f"{entry.path}: {entry.error}"
        for entry in task.entries
        if entry.error is not None
    ]
    if entry_errors:
        return "\n".join(entry_errors)
    if task.status is BackupStatus.PARTIALLY_SUCCEEDED:
        return "One or more backup entries failed."
    return "The backup task failed."
