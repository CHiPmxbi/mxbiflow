from .device_card import DeviceCard
from ....models.mxbi import MockDetectorModel


class MockDetectorCard(DeviceCard[MockDetectorModel]):
    def __init__(self):
        super().__init__()
        self.set_title("Mock Detector")

    def load_config(self, model: MockDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.detector_id))

    @property
    def result(self) -> MockDetectorModel:
        return MockDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            detector_id=int(self.line_device_id.text()),
        )
