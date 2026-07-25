from pymxbi.detector import MockDetectorModel

from ..device_card import DeviceCard


class MockDetectorCard(DeviceCard[MockDetectorModel]):
    def __init__(self) -> None:
        super().__init__()
        self.set_title("Mock Detector")

    def load_config(self, model: MockDetectorModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.id))

    @property
    def result(self) -> MockDetectorModel:
        return MockDetectorModel(
            enabled=self.checkbox_enabled.isChecked(),
            id=int(self.line_device_id.text()),
        )
