from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel

from ...models.mxbi import MXBIModel, MXBIPlatformEnum


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

        self._label_platform = QLabel("platform:")
        self._combo_platform = QComboBox()
        self._combo_platform.addItems([platform.value for platform in MXBIPlatformEnum])
        self._layout.addRow(self._label_platform, self._combo_platform)

        self._bind_events()

    def _emit_changed(self, msg: str) -> None:
        self.changed.emit(msg)

    def _bind_events(self) -> None:
        self._combo_mxbi.currentTextChanged.connect(self._emit_changed)
        self._combo_platform.currentTextChanged.connect(self._emit_changed)

    @property
    def mxbi_id(self) -> str:
        return self._combo_mxbi.currentText()

    @property
    def platform(self) -> str:
        return self._combo_platform.currentText()

    def load_from_model(self, model: MXBIModel) -> None:
        self._combo_mxbi.setCurrentText(str(model.mxbi_id))
        self._combo_platform.setCurrentText(str(model.platform))

    def apply_to_model(self, model: MXBIModel) -> None:
        mxbi_id_text = self._combo_mxbi.currentText().strip()
        try:
            model.mxbi_id = int(mxbi_id_text) if mxbi_id_text else 0
        except ValueError:
            model.mxbi_id = 0

        model.platform = MXBIPlatformEnum(self._combo_platform.currentText())
