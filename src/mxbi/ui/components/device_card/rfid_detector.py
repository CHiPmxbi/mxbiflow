from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
)

from .device_card import DeviceCard
from ....models.mxbi import RFIDDetectorModel


class RFIDDetectorCard(DeviceCard[RFIDDetectorModel]):
    def __init__(self):
        super().__init__()
        self.set_title("Single RFID Detector")

        lable_port = QLabel("Port:")
        self.comba_port = QComboBox()
        self.comba_port.addItems(["COM1", "COM2", "COM3", "COM4"])
        self.layout_config.addRow(lable_port, self.comba_port)

        lable_baudrate = QLabel("Baudrate:")
        self.comba_baudrate = QComboBox()
        self.comba_baudrate.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.layout_config.addRow(lable_baudrate, self.comba_baudrate)

    def load_config(self, model: RFIDDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.detector_id))
        self.comba_port.setCurrentText(model.port)
        self.comba_baudrate.setCurrentText(str(model.baudrate))

    @property
    def result(self) -> RFIDDetectorModel:
        return RFIDDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            detector_id=int(self.line_device_id.text()),
            port=self.comba_port.currentText(),
            baudrate=int(self.comba_baudrate.currentText()),
        )
