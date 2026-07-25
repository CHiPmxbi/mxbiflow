from pymxbi.detector import BeamBreakContinuousDetectorModel
from PySide6.QtWidgets import QLabel, QLineEdit

from ..device_card import DeviceCard


class BeambreakDetectorCard(DeviceCard[BeamBreakContinuousDetectorModel]):
    def __init__(self) -> None:
        super().__init__()

        self.set_title("Beambreak Detector")

        label_pin = QLabel("Pin")
        self._line_pin = QLineEdit()
        self._line_pin.setPlaceholderText("Pin")
        self.layout_config.addRow(label_pin, self._line_pin)

        label_animal_id = QLabel("Animal ID")
        self._line_animal_id = QLineEdit()
        self._line_animal_id.setPlaceholderText("Animal ID")
        self.layout_config.addRow(label_animal_id, self._line_animal_id)

        label_poll_interval = QLabel("Poll Interval")
        self._line_poll_interval = QLineEdit()
        self._line_poll_interval.setPlaceholderText("Poll Interval (s)")
        self.layout_config.addRow(label_poll_interval, self._line_poll_interval)

    def load_config(self, model: BeamBreakContinuousDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))
        self._line_pin.setText(str(model.pin))
        self._line_animal_id.setText(model.animal_id)
        self._line_poll_interval.setText(str(model.poll_interval))

    @property
    def result(self) -> BeamBreakContinuousDetectorModel:
        return BeamBreakContinuousDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
            pin=int(self._line_pin.text()),
            animal_id=self._line_animal_id.text(),
            poll_interval=float(self._line_poll_interval.text()),
        )
