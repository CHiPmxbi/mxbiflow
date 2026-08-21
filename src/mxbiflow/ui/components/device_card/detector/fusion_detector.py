from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from mxbiflow.driver.detector import FusionContinuousDetectorModel

from .....utils.serial import get_all_ports, get_baudrates
from ..device_card import DeviceCard


class FusionDetectorCard(DeviceCard[FusionContinuousDetectorModel]):
    def __init__(self) -> None:
        super().__init__(mount_base_fields=False)

        self.set_title("Fusion Detector")
        self.setMinimumWidth(400)

        self.checkbox_enabled.setText("Enabled")
        self.line_device_id.setMaximumWidth(64)

        self._line_pin = QLineEdit()
        self._line_pin.setPlaceholderText("Pin Number")
        self._line_pin.setMaximumWidth(64)

        self._combo_port = QComboBox()
        self._combo_port.addItems(get_all_ports())

        self._combo_baudrate = QComboBox()
        for text, value in get_baudrates():
            self._combo_baudrate.addItem(text, value)
        self._combo_baudrate.setMaximumWidth(112)

        self._line_poll_interval = QLineEdit()
        self._line_poll_interval.setPlaceholderText("Poll Interval (s)")
        self._line_poll_interval.setMaximumWidth(72)

        self._line_rfid_timeout = QLineEdit()
        self._line_rfid_timeout.setPlaceholderText("RFID Timeout (s)")
        self._line_rfid_timeout.setMaximumWidth(72)

        self._checkbox_leave_filter = QCheckBox("Enabled")
        self._spin_leave_filter_duration = QDoubleSpinBox()
        self._spin_leave_filter_duration.setAccessibleName("Leave filter duration")
        self._spin_leave_filter_duration.setRange(0.01, 60.0)
        self._spin_leave_filter_duration.setDecimals(2)
        self._spin_leave_filter_duration.setSingleStep(0.05)
        self._spin_leave_filter_duration.setSuffix(" s")
        self._spin_leave_filter_duration.setValue(0.2)
        self._spin_leave_filter_duration.setEnabled(False)

        self._compact_layout = QGridLayout()
        self._compact_layout.setContentsMargins(0, 0, 0, 0)
        self._compact_layout.setHorizontalSpacing(6)
        self._compact_layout.setVerticalSpacing(6)
        self._compact_layout.addWidget(self.checkbox_enabled, 0, 0)
        self._add_field(0, 1, "ID", self.line_device_id)
        self._add_field(0, 3, "Pin", self._line_pin)
        self._add_field(1, 0, "Port", self._combo_port, field_column_span=2)
        self._add_field(1, 3, "Baud", self._combo_baudrate)
        self._add_field(2, 0, "Poll", self._line_poll_interval)
        self._add_field(2, 2, "RFID Timeout", self._line_rfid_timeout)
        self._add_field(3, 0, "Leave Filter", self._checkbox_leave_filter)
        self._add_field(3, 2, "Duration", self._spin_leave_filter_duration)
        self._compact_layout.setColumnStretch(2, 1)
        self.layout_config.addRow(self._compact_layout)

        self._checkbox_leave_filter.toggled.connect(
            self._spin_leave_filter_duration.setEnabled
        )

    def _add_field(
        self,
        row: int,
        label_column: int,
        text: str,
        field: QWidget,
        *,
        field_column_span: int = 1,
    ) -> None:
        label = QLabel(text)
        label.setBuddy(field)
        self._compact_layout.addWidget(label, row, label_column)
        self._compact_layout.addWidget(
            field,
            row,
            label_column + 1,
            1,
            field_column_span,
        )

    def load_config(self, model: FusionContinuousDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self._line_pin.setText(str(model.pin))
        self._combo_port.setCurrentText(model.port)
        self._combo_baudrate.setCurrentText(str(model.baudrate))
        self._line_poll_interval.setText(str(model.poll_interval))
        self._line_rfid_timeout.setText(str(model.rfid_timeout))
        self._checkbox_leave_filter.setChecked(model.beam_break_filter_enabled)
        self._spin_leave_filter_duration.setValue(model.beam_break_filter_duration)

    @property
    def result(self) -> FusionContinuousDetectorModel:
        return FusionContinuousDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
            pin=int(self._line_pin.text()),
            port=self._combo_port.currentText(),
            baudrate=int(self._combo_baudrate.currentData()),
            poll_interval=float(self._line_poll_interval.text()),
            rfid_timeout=float(self._line_rfid_timeout.text()),
            beam_break_filter_enabled=self._checkbox_leave_filter.isChecked(),
            beam_break_filter_duration=self._spin_leave_filter_duration.value(),
        )
