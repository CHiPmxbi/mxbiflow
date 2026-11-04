from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mxbiflow.driver import MXBIModel
from mxbiflow.driver.detector import DetectorEnum, DetectorModel
from mxbiflow.driver.rewarder import RewarderEnum, RewarderModel

from ..core.config_store import ConfigStore
from ..core.path import (
    get_database_path,
    get_mxbi_config_path,
    get_mxbi_panel_config_path,
    get_offline_mxbi_config_path,
)
from ..models.database import MXBIDatabase
from ..models.panel import MXBIPanelConfig
from .components.baseconfig import BaseConfig
from .components.countdown import AutoAcceptCountdown
from .components.device_card import (
    BeambreakDetectorCard,
    FusionDetectorCard,
    MockDetectorCard,
    MockRewarderCard,
    RFIDDetectorCard,
    RPIGpioPumpCard,
)
from .components.devices import Devices


class MXBIPanel(QDialog):
    _REWARDER_CARD_FACTORIES: ClassVar[dict[str, type[QWidget]]] = {
        RewarderEnum.RPI_GPIO: RPIGpioPumpCard,
        RewarderEnum.MOCK: MockRewarderCard,
    }
    _DETECTOR_CARD_FACTORIES: ClassVar[dict[str, type[QWidget]]] = {
        DetectorEnum.RFID_CONTINUOUS: RFIDDetectorCard,
        DetectorEnum.BEAMBREAK_CONTINUOUS: BeambreakDetectorCard,
        DetectorEnum.FUSION_CONTINUOUS: FusionDetectorCard,
        DetectorEnum.MOCK: MockDetectorCard,
    }

    def __init__(self) -> None:
        super().__init__()
        self._database = ConfigStore(get_database_path(), MXBIDatabase)
        self._panel_config = ConfigStore(get_mxbi_panel_config_path(), MXBIPanelConfig)
        self._config = _hardware_store(self._panel_config.value.offline)

        self._build_ui()
        self._load_from_config()
        self._bind_events()

    def _build_ui(self) -> None:
        self.setWindowTitle("MXBI Configuration Panel")

        self._layout_main = QVBoxLayout(self)

        self.base_config = BaseConfig(self)
        self._layout_main.addWidget(self.base_config)
        self._build_device_groups()
        self._layout_main.addLayout(self._build_buttons_layout())

    def _build_device_groups(self) -> None:
        self.rewarders_group = Devices[RewarderModel](
            self,
            "Rewarders",
            action_label="Add Rewarder",
            device_types=list(RewarderEnum),
            dialog_title="Add rewarder",
            label="rewarder type:",
            card_factories=self._REWARDER_CARD_FACTORIES,
            columns=4,
        )
        self._layout_main.addWidget(self.rewarders_group)

        self.detectors_group = Devices[DetectorModel](
            self,
            "Detectors",
            action_label="Add Detector",
            device_types=list(DetectorEnum),
            dialog_title="Add detector",
            label="detector type:",
            card_factories=self._DETECTOR_CARD_FACTORIES,
            columns=4,
        )
        self._layout_main.addWidget(self.detectors_group)

    def _build_buttons_layout(self) -> QGridLayout:
        layout = QGridLayout()

        self._countdown = AutoAcceptCountdown(self)
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save")
        self.continue_button = QPushButton("Continue")

        layout.addWidget(self._countdown, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.cancel_button, 1, 0)
        layout.addWidget(self.save_button, 1, 1)
        layout.addWidget(self.continue_button, 1, 2)

        return layout

    @property
    def offline(self) -> bool:
        return self.base_config.check_offline.isChecked()

    def _load_from_config(self) -> None:
        self.base_config.check_offline.setChecked(self._panel_config.value.offline)
        self.base_config.load_auto_accept_timeout(
            self._panel_config.value.auto_accept_timeout_seconds
        )
        self._load_hardware()

    def _load_hardware(self) -> None:
        self.base_config.load_from_model(self._config.value)
        self.rewarders_group.load_models(self._config.value.rewarders)
        self.detectors_group.load_models(self._config.value.detectors)

    def _on_offline_toggled(self, offline: bool) -> None:
        # Each mode has its own file; neither is written until Save or Continue.
        self._config = _hardware_store(offline)
        self.rewarders_group.clear()
        self.detectors_group.clear()
        self._load_hardware()

    def _collect_result(self) -> None:
        self.base_config.apply_to_model(self._config.value)

        self._config.value.rewarders = self.rewarders_group.results()
        self._config.value.detectors = self.detectors_group.results()

    def _on_save(self) -> None:
        self._collect_result()
        self._config.save()
        self._save_panel_config()

    def _on_continue(self) -> None:
        self._on_save()
        self.accept()

    def _save_panel_config(self) -> None:
        self._panel_config.value.auto_accept_timeout_seconds = (
            self.base_config.auto_accept_timeout
        )
        self._panel_config.value.offline = self.offline
        self._panel_config.save()

    def _start_auto_accept_countdown(self) -> None:
        self._countdown.start(self._panel_config.value.auto_accept_timeout_seconds)

    def _bind_events(self) -> None:
        self.base_config.check_offline.toggled.connect(self._on_offline_toggled)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.save_button.clicked.connect(self._on_save)
        self.continue_button.clicked.connect(self._on_continue)
        self._countdown.timeout.connect(self._on_continue)

    def _on_cancel(self) -> None:
        self.reject()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._start_auto_accept_countdown()

    def done(self, result: int) -> None:
        self._countdown.stop()
        super().done(result)


def _hardware_store(offline: bool) -> ConfigStore[MXBIModel]:
    path = get_offline_mxbi_config_path() if offline else get_mxbi_config_path()
    return ConfigStore(path, MXBIModel)
