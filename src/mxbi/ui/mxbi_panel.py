from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..path import MXBI_CONFIG_PATH, OPTIONS_PATH
from ..config import Configure
from ..models.mxbi import (
    DetectorModel,
    DetectorTypeEnum,
    MXBIModel,
    RewarderModel,
    RewarderTypeEnum,
)
from ..models.session import Options
from .components.baseconfig import BaseConfig
from .components.device_card import (
    MockRewarderCard,
    GPIOPumpCard,
    MockDetectorCard,
    RFIDDetectorCard,
)
from .components.devices import Devices


class MXBIPanel(QMainWindow):
    accepted = Signal()

    _REWARDER_CARD_FACTORIES: dict[str, type[QWidget]] = {
        RewarderTypeEnum.GPIO_REWARDER: GPIOPumpCard,
        RewarderTypeEnum.MOCK_REWARDER: MockRewarderCard,
    }
    _DETECTOR_CARD_FACTORIES: dict[str, type[QWidget]] = {
        DetectorTypeEnum.MOCK_DETECTOR: MockDetectorCard,
        DetectorTypeEnum.RFID_DETECTOR: RFIDDetectorCard,
    }

    # -----------------------------
    # Lifecycle / Init
    # -----------------------------

    def __init__(self):
        super().__init__()
        self._config = Configure(MXBI_CONFIG_PATH, MXBIModel)
        self._options = Configure(OPTIONS_PATH, Options)

        self._build_ui()
        self._load_from_config()
        self._bind_events()

    # -----------------------------
    # UI Construction
    # -----------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("MXBI Configuration Panel")

        self._widget_main = QWidget()
        self._layout_main = QVBoxLayout()
        self._widget_main.setLayout(self._layout_main)
        self.setCentralWidget(self._widget_main)

        self.base_config = BaseConfig(self, self._options.value.mxbis)
        self._layout_main.addWidget(self.base_config)
        self._build_device_groups()
        self._layout_main.addLayout(self._build_buttons_row())

    def _build_device_groups(self) -> None:
        self.rewarders_group = Devices[RewarderModel](
            self,
            "Rewarders",
            action_label="Add Rewarder",
            device_types=[
                RewarderTypeEnum.GPIO_REWARDER,
                RewarderTypeEnum.MOCK_REWARDER,
            ],
            dialog_title="Add rewarder",
            label="rewarder type:",
            card_factories=self._REWARDER_CARD_FACTORIES,
        )
        self._layout_main.addWidget(self.rewarders_group)

        self.detectors_group = Devices[DetectorModel](
            self,
            "Detectors",
            action_label="Add Detector",
            device_types=[
                DetectorTypeEnum.MOCK_DETECTOR,
                DetectorTypeEnum.RFID_DETECTOR,
            ],
            dialog_title="Add detector",
            label="detector type:",
            card_factories=self._DETECTOR_CARD_FACTORIES,
        )
        self._layout_main.addWidget(self.detectors_group)

    def _build_buttons_row(self) -> QHBoxLayout:
        layout_buttons = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        self.continue_button = QPushButton("Continue")
        layout_buttons.addWidget(self.cancel_button)
        layout_buttons.addWidget(self.save_button)
        layout_buttons.addWidget(self.continue_button)
        return layout_buttons

    # -----------------------------
    # Load / Save
    # -----------------------------

    def _load_from_config(self) -> None:
        self.base_config.load_from_model(self._config.value)

        self.rewarders_group.load_models(self._config.value.rewarders)
        self.detectors_group.load_models(self._config.value.detectors)

    def _collect_result(self) -> None:
        self.base_config.apply_to_model(self._config.value)

        # Replace instead of append so repeated Save/Continue doesn't duplicate entries.
        self._config.value.rewarders = self.rewarders_group.results()
        self._config.value.detectors = self.detectors_group.results()

    def _on_save(self) -> None:
        self._collect_result()
        self._config.save()

    def _on_continue(self) -> None:
        self._collect_result()
        self._config.save()
        self.close()
        self.accepted.emit()

    # -----------------------------
    # Events / Menus
    # -----------------------------

    def _bind_events(self) -> None:
        self.cancel_button.clicked.connect(self._on_cancel)
        self.save_button.clicked.connect(self._on_save)
        self.continue_button.clicked.connect(self._on_continue)

    def _on_cancel(self) -> None:
        self.close()


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = MXBIPanel()
    window.show()
    sys.exit(app.exec())
