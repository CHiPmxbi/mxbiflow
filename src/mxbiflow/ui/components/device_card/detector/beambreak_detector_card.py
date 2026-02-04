from PySide6.QtWidgets import QLabel, QLineEdit


from pymxbi.detector import FusionContinuousDetectorModel
from ..device_card import DeviceCard


class BeambreakDetectorCard(DeviceCard[FusionContinuousDetectorModel]):
    def __init__(self):
        super().__init__()

        self.set_title("Beambreak Detector")

        label_pin = QLabel("Pin")
        self._line_pin = QLineEdit()
        self._line_pin.setPlaceholderText("Pin")
        self.layout_config.addRow(label_pin, self._line_pin)

    def load_config(self, model: FusionContinuousDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self._line_pin.setText(str(model.pin))

    @property
    def result(self) -> FusionContinuousDetectorModel:
        return FusionContinuousDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
            pin=int(self._line_pin.text()),
        )
