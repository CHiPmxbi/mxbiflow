from __future__ import annotations

from pymxbi import MXBIModel
from pymxbi.screen import get_screen_size
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel


class BaseConfig(QGroupBox):
    changed = Signal(str)

    def __init__(self, parent, mxbi_options: list[str]):
        super().__init__(parent)

        self.setTitle("Base config")

        self._layout = QFormLayout()
        self.setLayout(self._layout)

        self._label_mxbi = QLabel("mxbi id:")
        self._combo_mxbi = QComboBox()
        self._combo_mxbi.addItems(mxbi_options)
        self._layout.addRow(self._label_mxbi, self._combo_mxbi)

        self._label_screen = QLabel("screen:")
        self._combo_screen = QComboBox()

        for screen in get_screen_size():
            self._combo_screen.addItem(
                f"{screen.width} * {screen.height}", (screen.width, screen.height)
            )
        self._layout.addRow(self._label_screen, self._combo_screen)

        self._bind_events()

    def _emit_changed(self, msg: str) -> None:
        self.changed.emit(msg)

    def _bind_events(self) -> None:
        self._combo_mxbi.currentTextChanged.connect(self._emit_changed)
        self._combo_screen.currentTextChanged.connect(self._emit_changed)

    @property
    def mxbi_id(self) -> str:
        return self._combo_mxbi.currentText()

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._combo_screen.currentData()

    def load_from_model(self, model: MXBIModel) -> None:
        self._combo_mxbi.setCurrentText(model.mxbi_id)
        for i in range(self._combo_screen.count()):
            if self._combo_screen.itemData(i) == tuple(model.screen_size):
                self._combo_screen.setCurrentIndex(i)
                break

    def apply_to_model(self, model: MXBIModel) -> None:
        mxbi_id_text = self._combo_mxbi.currentText().strip()
        try:
            model.mxbi_id = int(mxbi_id_text) if mxbi_id_text else 0
        except ValueError:
            model.mxbi_id = 0

        model.screen_size = self._combo_screen.currentData()
