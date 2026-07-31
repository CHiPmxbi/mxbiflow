import sys

from pymotego import (
    BackupDestination,
    BackupSource,
    BackupStatus,
    BackupTask,
)
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..infra.backup import BackupTaskRunner

_REFRESH_INTERVAL_MS = 250
_SUCCESS_AUTO_CLOSE_MS = 10_000


def run_backup(
    source: BackupSource,
    destination: BackupDestination,
    *,
    poll_interval_s: float = 1.0,
    max_attempts: int = 3,
    refresh_interval_ms: int = _REFRESH_INTERVAL_MS,
    success_auto_close_ms: int = _SUCCESS_AUTO_CLOSE_MS,
) -> None:
    """Create a backup and show a blocking progress dialog."""
    runner = BackupTaskRunner(
        poll_interval_s=poll_interval_s,
        max_attempts=max_attempts,
    )
    runner.start(source, destination)
    _show_progress_dialog(
        runner,
        refresh_interval_ms=refresh_interval_ms,
        success_auto_close_ms=success_auto_close_ms,
    )


def _show_progress_dialog(
    runner: BackupTaskRunner,
    *,
    refresh_interval_ms: int,
    success_auto_close_ms: int,
) -> None:
    application = _require_application()
    dialog = _BackupProgressDialog(
        runner,
        refresh_interval_ms=refresh_interval_ms,
        success_auto_close_ms=success_auto_close_ms,
    )
    dialog.finished.connect(application.quit)
    dialog.show()
    application.exec()


def _require_application() -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    if not isinstance(application, QApplication):
        raise TypeError("The active Qt application is not a QApplication")
    return application


class _BackupProgressDialog(QDialog):
    def __init__(
        self,
        runner: BackupTaskRunner,
        *,
        refresh_interval_ms: int = _REFRESH_INTERVAL_MS,
        success_auto_close_ms: int = _SUCCESS_AUTO_CLOSE_MS,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._can_close = False
        self._terminal_state_shown = False
        self._success_auto_close_ms = success_auto_close_ms
        self._remaining_seconds = 0

        self._build_ui()
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)

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

        self._error_label = QLabel("", self)
        self._error_label.setWordWrap(True)
        self._error_label.setAccessibleName("Backup error")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._close_button = QPushButton("Close", self)
        self._close_button.clicked.connect(self.accept)
        self._close_button.hide()
        buttons.addWidget(self._close_button)
        layout.addLayout(buttons)

    def _refresh(self) -> None:
        task = self._runner.latest_task
        if task is None:
            return

        self._update_progress(task)
        self._update_details(task)

        if self._terminal_state_shown:
            return

        if task.status is BackupStatus.SUCCEEDED:
            self._show_success()
        elif task.status in {
            BackupStatus.PARTIALLY_SUCCEEDED,
            BackupStatus.FAILED,
        }:
            self._show_failure(_task_failure_message(task))
        elif not self._runner.is_monitoring:
            error = self._runner.error
            message = (
                str(error)
                if error is not None
                else "Backup monitoring stopped before the task completed."
            )
            self._show_failure(message)

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
        self._countdown_label.setText("Auto-close cancelled")
        self._close_button.show()
        self._close_button.setFocus()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            self._stop_auto_close()
        return super().eventFilter(obj, event)

    def _show_failure(self, message: str) -> None:
        self._terminal_state_shown = True
        self._can_close = True
        self._refresh_timer.stop()
        self._auto_close_timer.stop()
        self._status_label.setText("Backup requires attention")
        self._error_label.setText(message)
        self._error_label.show()
        self._close_button.show()
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
