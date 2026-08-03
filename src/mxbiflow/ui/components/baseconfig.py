from __future__ import annotations

import socket

from pymxbi import MXBIModel
from pymxbi.screen import get_screen_size
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QWidget,
)


class BaseConfig(QGroupBox):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)

        self.setTitle("Base config")

        self._layout = QFormLayout()
        self.setLayout(self._layout)

        self._label_mxbi = QLabel("mxbi id:")
        self._value_mxbi = QLabel(self.mxbi_id)
        self._layout.addRow(self._label_mxbi, self._value_mxbi)

        self._label_screen = QLabel("screen:")
        self._combo_screen = QComboBox()

        for screen in get_screen_size():
            self._combo_screen.addItem(
                f"{screen.width} * {screen.height}", (screen.width, screen.height)
            )
        self._layout.addRow(self._label_screen, self._combo_screen)

        self._label_auto_accept = QLabel("auto accept (s):")
        self._spin_auto_accept = QSpinBox()
        self._spin_auto_accept.setRange(0, 3600)
        self._spin_auto_accept.setSpecialValueText("Disabled")
        self._layout.addRow(self._label_auto_accept, self._spin_auto_accept)

    @property
    def mxbi_id(self) -> str:
        return socket.gethostname()

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._combo_screen.currentData()

    @property
    def auto_accept_timeout(self) -> int:
        return self._spin_auto_accept.value()

    def load_from_model(self, model: MXBIModel) -> None:
        for i in range(self._combo_screen.count()):
            if self._combo_screen.itemData(i) == tuple(model.screen_size):
                self._combo_screen.setCurrentIndex(i)
                break

    def load_auto_accept_timeout(self, timeout_seconds: int) -> None:
        self._spin_auto_accept.setValue(timeout_seconds)

    def apply_to_model(self, model: MXBIModel) -> None:
        model.mxbi_id = self.mxbi_id
        model.screen_size = self._combo_screen.currentData()
