from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

from mxbiflow.driver.detector import FusionContinuousDetectorModel

from .....utils.serial import get_all_ports, get_baudrates
from ..device_card import DeviceCard


class FusionDetectorCard(DeviceCard[FusionContinuousDetectorModel]):
    def __init__(self) -> None:
        super().__init__()

        self.set_title("Fusion Detector")

        label_pin = QLabel("Beam Break Pin")
        self._line_pin = QLineEdit()
        self._line_pin.setPlaceholderText("Pin Number")
        self.layout_config.addRow(label_pin, self._line_pin)

        label_port = QLabel("Port")
        self._combo_port = QComboBox()
        self._combo_port.addItems(get_all_ports())
        self.layout_config.addRow(label_port, self._combo_port)

        label_baudrate = QLabel("Baudrate")
        self._combo_baudrate = QComboBox()
        for text, value in get_baudrates():
            self._combo_baudrate.addItem(text, value)
        self.layout_config.addRow(label_baudrate, self._combo_baudrate)

        label_poll_interval = QLabel("Poll Interval")
        self._line_poll_interval = QLineEdit()
        self._line_poll_interval.setPlaceholderText("Poll Interval (s)")
        self.layout_config.addRow(label_poll_interval, self._line_poll_interval)

        label_rfid_timeout = QLabel("RFID Timeout")
        self._line_rfid_timeout = QLineEdit()
        self._line_rfid_timeout.setPlaceholderText("RFID Timeout (s)")
        self.layout_config.addRow(label_rfid_timeout, self._line_rfid_timeout)

    def load_config(self, model: FusionContinuousDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self._line_pin.setText(str(model.pin))
        self._combo_port.setCurrentText(model.port)
        self._combo_baudrate.setCurrentText(str(model.baudrate))
        self._line_poll_interval.setText(str(model.poll_interval))
        self._line_rfid_timeout.setText(str(model.rfid_timeout))

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
        )
