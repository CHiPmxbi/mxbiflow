from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
)

from ..device_card import DeviceCard
from .....models.mxbi import RFIDContinuousDetectorModel
from .....utils.serial import get_baudrates, get_all_ports


class RFIDDetectorCard(DeviceCard[RFIDContinuousDetectorModel]):
    def __init__(self):
        super().__init__()
        self.set_title("Single RFID Detector")

        lable_port = QLabel("Port:")
        self.combo_port = QComboBox()
        self.combo_port.addItems(get_all_ports())
        self.layout_config.addRow(lable_port, self.combo_port)

        lable_baudrate = QLabel("Baudrate:")
        self.combo_baudrate = QComboBox()
        for text, value in get_baudrates():
            self.combo_baudrate.addItem(text, value)
        self.layout_config.addRow(lable_baudrate, self.combo_baudrate)

    def load_config(self, model: RFIDContinuousDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self.combo_port.setCurrentText(model.port)
        self.combo_baudrate.setCurrentText(str(model.baudrate))

    @property
    def result(self) -> RFIDContinuousDetectorModel:
        return RFIDContinuousDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
            port=self.combo_port.currentText(),
            baudrate=int(self.combo_baudrate.currentText()),
        )
