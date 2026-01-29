from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QDialogButtonBox,
)

from collections.abc import Sequence


class AddDeviceDialog(QDialog):
    """
    Simple picker dialog.

    `device_types` items can be either strings or StrEnum members (since they are `str`).
    """

    def __init__(
        self,
        parent=None,
        *,
        device_types: Sequence[str],
        title: str = "Add device",
        label: str = "device type:",
    ):
        super().__init__(parent)
        self._device_types = device_types
        self._title = title
        self._label = label
        self._init_ui()
        self._bind_events()

    def _init_ui(self):
        self.setWindowTitle(self._title)

        self._main_layout = QVBoxLayout()
        self.setLayout(self._main_layout)

        self._layout_type = QFormLayout()
        self._main_layout.addLayout(self._layout_type)

        self._label_device_type = QLabel(self._label)
        self._comba_device_type = QComboBox()
        self._comba_device_type.addItems([str(item) for item in self._device_types])
        self._layout_type.addRow(self._label_device_type, self._comba_device_type)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._main_layout.addWidget(self.button_box)

    def _bind_events(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    @property
    def device_type(self) -> str:
        return self._comba_device_type.currentText()

    @property
    def selected_device(self) -> str:
        return self.device_type
