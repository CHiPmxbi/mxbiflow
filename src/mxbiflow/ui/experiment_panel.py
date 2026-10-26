from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QPushButton,
    QVBoxLayout,
)

from ..core.config_store import ConfigStore
from ..core.path import (
    get_config_session_path,
    get_database_path,
    get_mxbi_panel_config_path,
)
from ..infra.cogmote_config import read_experiment_config
from ..models.database import MXBIDatabase
from ..models.experiment import ExperimentAnimal
from ..models.panel import MXBIPanelConfig
from ..models.session import SessionConfig
from ..scene import SceneManager
from ..utils.logger import logger
from .components.countdown import AutoAcceptCountdown
from .components.experiment_groups import (
    ExperimentAnimalsGroup,
    ExperimentConfigGroup,
    ExperimentSceneGroup,
)


class ExperimentPanel(QDialog):
    def __init__(self, scene_manager: SceneManager) -> None:
        super().__init__()
        self._config = ConfigStore(get_config_session_path(), SessionConfig)
        self._database = ConfigStore(get_database_path(), MXBIDatabase)
        self._stage_level_tables = scene_manager.stage_level_tables

        self.setWindowTitle("Experiment Panel")

        layout_main = QVBoxLayout(self)

        self.group_config = ExperimentConfigGroup(
            self, self._database.value.experimenter
        )
        layout_main.addWidget(self.group_config)

        self.group_scene = ExperimentSceneGroup(
            self,
            stages=list(self._stage_level_tables.keys()),
        )
        layout_main.addWidget(self.group_scene)

        self.group_animals = ExperimentAnimalsGroup(
            self,
            animals=_configured_animals(),
            stage_level_tables=self._stage_level_tables,
        )
        layout_main.addWidget(self.group_animals)

        self.combo_experimenter = self.group_config.combo_experimenter
        self.combo_reward_type = self.group_config.combo_reward_type
        self.line_notes = self.group_config.line_notes

        layout_buttons = QGridLayout()
        layout_main.addLayout(layout_buttons)

        self._countdown = AutoAcceptCountdown(self)
        self._button_cancel = QPushButton("Cancel", self)
        self._button_save = QPushButton("Save", self)
        self._button_continue = QPushButton("Continue", self)

        layout_buttons.addWidget(
            self._countdown, 0, 2, alignment=Qt.AlignmentFlag.AlignRight
        )
        layout_buttons.addWidget(self._button_cancel, 1, 0)
        layout_buttons.addWidget(self._button_save, 1, 1)
        layout_buttons.addWidget(self._button_continue, 1, 2)

        self._bind_signals()
        self.load_config()

    def _bind_signals(self) -> None:
        self._button_cancel.clicked.connect(self._on_cancel)
        self._button_save.clicked.connect(self._on_save)
        self._button_continue.clicked.connect(self._on_continue)
        self._countdown.timeout.connect(self._on_continue)

    def load_config(self) -> None:
        self.group_config.load_config(self._config.value)
        self.group_scene.load_config(self._config.value)
        self.group_animals.load_config(self._config.value)

    def _collect_result(self) -> SessionConfig:
        session_config = self.group_config.result()
        scene_result = self.group_scene.result()
        data = session_config.model_dump()
        data.update(
            default_scene=scene_result.default_scene,
            fault_fallback=scene_result.fault_fallback,
            animals=self.group_animals.result(),
        )
        return SessionConfig.model_validate(data)

    def _on_save(self) -> None:
        self._config.save(self._collect_result())

    def _on_cancel(self) -> None:
        self.reject()

    def _on_continue(self) -> None:
        self._on_save()
        self.accept()

    def _start_auto_accept_countdown(self) -> None:
        panel_config = ConfigStore(get_mxbi_panel_config_path(), MXBIPanelConfig).value
        self._countdown.start(panel_config.auto_accept_timeout_seconds)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._start_auto_accept_countdown()

    def done(self, result: int) -> None:
        self._countdown.stop()
        super().done(result)


def _configured_animals() -> tuple[ExperimentAnimal, ...]:
    """The cage's animals from the cogmote configuration, with their RFID tags."""
    try:
        experiment = read_experiment_config()
    except Exception as error:  # noqa: BLE001 - cogmoteGO may be absent; the wizard still opens
        logger.warning("cannot read the cogmote experiment configuration: %s", error)
        return ()
    if experiment is None:
        logger.warning(
            "no experiment is configured in cogmote; the wizard has no animals"
        )
        return ()
    return experiment.animals
