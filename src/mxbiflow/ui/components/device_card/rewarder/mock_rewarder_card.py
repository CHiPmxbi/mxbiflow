from .device_card import DeviceCard

from ....models.mxbi import MockRewarderModel


class MockRewarderCard(DeviceCard[MockRewarderModel]):
    def __init__(self):
        super().__init__()
        self.set_title("Mock Rewarder")

    def load_config(self, model: MockRewarderModel) -> None:
        self.checkbox_enabled.setChecked(model.enabled)
        self.line_device_id.setText(str(model.rewarder_id))

    @property
    def result(self) -> MockRewarderModel:
        return MockRewarderModel(
            enabled=self.checkbox_enabled.isChecked(),
            rewarder_id=int(self.line_device_id.text()),
        )
