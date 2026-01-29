from __future__ import annotations

from typing import Generic, TypeVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QVBoxLayout,
)

from ..card import CardFrame

TModel = TypeVar("TModel")


class DeviceCard(CardFrame, Generic[TModel]):
    remove_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent, object_name="card")

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

        self.layout_main = QVBoxLayout()
        self.setLayout(self.layout_main)
        self.layout_main.setContentsMargins(8, 8, 8, 8)

        self.label_title = QLabel("Device Configuration")
        self.layout_main.addWidget(self.label_title)

        self.layout_config = QFormLayout()
        self.layout_main.addLayout(self.layout_config)

        self.lable_enabled = QLabel("Enabled:")
        self.checkbox_enabled = QCheckBox()
        self.checkbox_enabled.setChecked(False)
        self.layout_config.addRow(self.lable_enabled, self.checkbox_enabled)

        self.label_id = QLabel("Device ID:")
        self.line_device_id = QLineEdit("0")
        self.int_validator = QIntValidator(0, 1000, self)
        self.line_device_id.setValidator(self.int_validator)
        self.layout_config.addRow(self.label_id, self.line_device_id)

    def _open_menu(self, position) -> None:
        menu = QMenu(self)
        action_remove = menu.addAction("Remove")
        action_remove.triggered.connect(
            lambda _checked=False: self.remove_requested.emit()
        )
        menu.exec(self.mapToGlobal(position))

    def set_title(self, title: str) -> None:
        self.label_title.setText(title)

    def load_config(self, model: TModel) -> None:
        raise NotImplementedError

    @property
    def result(self) -> TModel:
        raise NotImplementedError
