from collections.abc import Callable, Mapping
from enum import StrEnum, auto
from threading import Lock, Thread

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..infra.post_processing import StagePostProcessor, send_session_report
from ..models.session import Session
from .application import require_application

_REFRESH_INTERVAL_MS = 250
_SUCCESS_AUTO_CLOSE_MS = 10_000
_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")


class _StepStatus(StrEnum):
    PENDING = auto()
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    SKIPPED = auto()


class _ActionRunner:
    def __init__(self, action: Callable[[], None], *, enabled: bool) -> None:
        self._action = action
        self._lock = Lock()
        self._status = _StepStatus.PENDING if enabled else _StepStatus.SKIPPED
        self._error: Exception | None = None

    @property
    def status(self) -> _StepStatus:
        with self._lock:
            return self._status

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    def start(self) -> None:
        with self._lock:
            if self._status is not _StepStatus.PENDING:
                return
            self._status = _StepStatus.RUNNING
        Thread(target=self._run, name="session-report", daemon=True).start()

    def _run(self) -> None:
        try:
            self._action()
        except Exception as error:  # noqa: BLE001 - displayed by the panel
            with self._lock:
                self._error = error
                self._status = _StepStatus.FAILED
        else:
            with self._lock:
                self._status = _StepStatus.SUCCEEDED


def run_session_post_processing(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> None:
    """Send the daily report for a completed session."""
    _application = require_application()
    PostProcessingPanel(session, stage_post_processors).exec()


class PostProcessingPanel(QDialog):
    def __init__(
        self,
        session: Session,
        stage_post_processors: Mapping[str, StagePostProcessor],
        *,
        refresh_interval_ms: int = _REFRESH_INTERVAL_MS,
        success_auto_close_ms: int = _SUCCESS_AUTO_CLOSE_MS,
    ) -> None:
        super().__init__()
        self._report_runner = _ActionRunner(
            lambda: send_session_report(session, stage_post_processors),
            enabled=session.send_email,
        )
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

        self._report_runner.start()
        self._refresh()
        self._refresh_timer.start()

    def _build_ui(self) -> None:
        self.setWindowTitle("Session Post-processing")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.resize(560, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self._status_label = QLabel("Post-processing in progress", self)
        font = self._status_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self._status_label.setFont(font)
        layout.addWidget(self._status_label)

        self._countdown_label = QLabel("", self)
        self._countdown_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self._countdown_label.hide()
        layout.addWidget(self._countdown_label)

        self._report_status_label = QLabel("Daily report: Waiting", self)
        self._report_status_label.setAccessibleName("Daily report status")
        layout.addWidget(self._report_status_label)

        self._error_label = QLabel("", self)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #C62828;")
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
        self._refresh_report()

        status = self._report_runner.status
        if self._terminal_state_shown or status in {
            _StepStatus.PENDING,
            _StepStatus.RUNNING,
        }:
            return

        error = self._report_runner.error
        if error is not None:
            self._show_failure(str(error))
        else:
            self._show_success()

    def _refresh_report(self) -> None:
        match self._report_runner.status:
            case _StepStatus.PENDING:
                self._report_status_label.setText("Daily report: Waiting")
            case _StepStatus.RUNNING:
                self._set_running_label(self._report_status_label, "Daily report")
            case _StepStatus.SUCCEEDED:
                self._set_succeeded_label(self._report_status_label, "Daily report")
            case _StepStatus.FAILED:
                self._set_failed_label(self._report_status_label, "Daily report")
            case _StepStatus.SKIPPED:
                self._report_status_label.setStyleSheet("color: #666666;")
                self._report_status_label.setText("Daily report: Skipped")

    def _set_running_label(self, label: QLabel, name: str) -> None:
        frame = _SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)]
        self._spinner_index += 1
        label.setStyleSheet("")
        label.setText(f"{frame} {name}: In progress")

    @staticmethod
    def _set_succeeded_label(label: QLabel, name: str) -> None:
        label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        label.setText(f"✓ {name}: Done")

    @staticmethod
    def _set_failed_label(label: QLabel, name: str) -> None:
        label.setStyleSheet("color: #C62828; font-weight: bold;")
        label.setText(f"✕ {name}: Failed")

    def _show_success(self) -> None:
        self._terminal_state_shown = True
        self._can_close = True
        self._refresh_timer.stop()
        self._status_label.setText("Post-processing completed.")
        self._stop_countdown_button.setEnabled(True)
        self._close_button.setEnabled(True)
        if self._success_auto_close_ms > 0:
            self._start_countdown()
        self._auto_close_timer.start(self._success_auto_close_ms)

    def _start_countdown(self) -> None:
        self._remaining_seconds = max(1, round(self._success_auto_close_ms / 1000))
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
        self._countdown_timer.stop()
        self._auto_close_timer.stop()
        self._stop_countdown_button.setEnabled(False)
        self._close_button.setFocus()

    def _show_failure(self, message: str) -> None:
        self._terminal_state_shown = True
        self._can_close = True
        self._refresh_timer.stop()
        self._auto_close_timer.stop()
        self._status_label.setText("Post-processing requires attention")
        self._error_label.setText(message)
        self._error_label.show()
        self._close_button.setEnabled(True)
        self._close_button.setFocus()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._can_close:
            event.ignore()
            return
        super().closeEvent(event)
