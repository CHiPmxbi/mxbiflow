from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
)

from mxbiflow.driver.rewarder import GPIORewarderModel

from ..device_card import DeviceCard


class RPIGpioPumpCard(DeviceCard[GPIORewarderModel]):
    def __init__(self) -> None:
        super().__init__()
        self.set_title("GPIO Pump")

        lable_gpio_pin = QLabel("GPIO Pin:")
        self.line_gpio_pin = QLineEdit("0")
        int_validator = QIntValidator(0, 40, self)
        self.line_gpio_pin.setValidator(int_validator)
        self.layout_config.addRow(lable_gpio_pin, self.line_gpio_pin)

    def load_config(self, model: GPIORewarderModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self.line_gpio_pin.setText(str(model.pin))

    @property
    def result(self) -> GPIORewarderModel:
        return GPIORewarderModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
            pin=int(self.line_gpio_pin.text()),
        )
