from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class AutoAcceptCountdown(QWidget):
    timeout = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._remaining_seconds = 0
        self._is_paused = False
        self._is_active = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("", self)
        self._label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self._label)

        self.hide()

    def start(self, seconds: int) -> None:
        if seconds <= 0:
            self.stop()
            return

        self._remaining_seconds = seconds
        self._is_paused = False
        self._is_active = True
        self._update_label()
        self.show()
        self._timer.start()

    def pause(self) -> None:
        if not self._is_active or self._is_paused:
            return

        self._is_paused = True
        self._timer.stop()
        self._update_label()

    def stop(self) -> None:
        self._timer.stop()
        self._is_paused = False
        self._is_active = False
        self._remaining_seconds = 0
        self.hide()

    def is_active(self) -> bool:
        return self._is_active and not self._is_paused

    def _tick(self) -> None:
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._timer.stop()
            self._is_active = False
            self.hide()
            self.timeout.emit()
        else:
            self._update_label()

    def _update_label(self) -> None:
        if self._is_paused:
            self._label.setText(f"Paused: {self._remaining_seconds}s")
            self._label.setStyleSheet("color: #9E9E9E; font-weight: bold;")
        else:
            self._label.setText(f"Auto: {self._remaining_seconds}s")
            self._label.setStyleSheet("color: #4CAF50; font-weight: bold;")
