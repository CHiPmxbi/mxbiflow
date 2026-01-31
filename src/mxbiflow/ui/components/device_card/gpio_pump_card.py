from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
)

from PySide6.QtGui import QIntValidator
from .device_card import DeviceCard
from ....models.mxbi import GPIORewarderModel


class GPIOPumpCard(DeviceCard[GPIORewarderModel]):
    def __init__(self):
        super().__init__()
        self.set_title("GPIO Pump")

        lable_gpio_pin = QLabel("GPIO Pin:")
        self.line_gpio_pin = QLineEdit("0")
        int_validator = QIntValidator(0, 40, self)
        self.line_gpio_pin.setValidator(int_validator)
        self.layout_config.addRow(lable_gpio_pin, self.line_gpio_pin)

    def load_config(self, model: GPIORewarderModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.rewarder_id))
        self.line_gpio_pin.setText(str(model.pin))

    @property
    def result(self) -> GPIORewarderModel:
        return GPIORewarderModel(
            enabled=self.checkbox_enabled.isChecked(),
            rewarder_id=int(self.line_device_id.text()),
            pin=int(self.line_gpio_pin.text()),
        )
