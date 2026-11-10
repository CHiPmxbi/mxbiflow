from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..core.config_store import ConfigStore
from ..core.offline import is_offline
from ..core.path import (
    get_config_session_path,
    get_database_path,
    get_mxbi_panel_config_path,
)
from ..infra.cogmote_config import read_experiment_config
from ..models.database import MXBIDatabase
from ..models.panel import MXBIPanelConfig
from ..models.session import SessionConfig
from ..scene import SceneManager
from ..utils.logger import logger
from .components.animal import AnimalOption
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

        self._animals = (
            _database_animals(self._database.value)
            if is_offline()
            else _configured_animals()
        )
        self.group_scene = ExperimentSceneGroup(
            self,
            stages=list(self._stage_level_tables.keys()),
            animals=[animal.name for animal in self._animals],
        )
        layout_main.addWidget(self.group_scene)

        self.group_animals = ExperimentAnimalsGroup(
            self,
            animals=self._animals,
            stage_level_tables=self._stage_level_tables,
        )
        layout_main.addWidget(self.group_animals)

        self.combo_experimenter = self.group_config.combo_experimenter
        self.combo_reward_type = self.group_config.combo_reward_type
        self.line_notes = self.group_config.line_notes

        self.label_error = QLabel("", self)
        self.label_error.setStyleSheet("color: #F44336;")
        self.label_error.setWordWrap(True)
        layout_main.addWidget(self.label_error)

        layout_buttons = QGridLayout()
        layout_main.addLayout(layout_buttons)

        self._countdown = AutoAcceptCountdown(self)
        self._button_cancel = QPushButton("Cancel", self)
        self._button_save = QPushButton("Save", self)
        self.button_continue = QPushButton("Continue", self)

        layout_buttons.addWidget(
            self._countdown, 0, 2, alignment=Qt.AlignmentFlag.AlignRight
        )
        layout_buttons.addWidget(self._button_cancel, 1, 0)
        layout_buttons.addWidget(self._button_save, 1, 1)
        layout_buttons.addWidget(self.button_continue, 1, 2)

        self._bind_signals()
        self.load_config()

    def _bind_signals(self) -> None:
        self._button_cancel.clicked.connect(self._on_cancel)
        self._button_save.clicked.connect(self._on_save)
        self.button_continue.clicked.connect(self._on_continue)
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
            unknown_animal_as=scene_result.unknown_animal_as,
            fault_fallback=scene_result.fault_fallback,
            animals=self.group_animals.result(),
        )
        return SessionConfig.model_validate(data)

    def _on_save(self) -> bool:
        """Save the configuration, or say why it cannot be saved."""
        if not is_offline() and not self._animals:
            self.label_error.setText(
                "cogmote offers no animals: cogmoteGO is unreachable or no experiment "
                "is configured. Turn on Offline on the first panel to use the local "
                "configuration."
            )
            return False
        try:
            config = self._collect_result()
        except ValidationError as error:
            self.label_error.setText(
                "; ".join(detail["msg"] for detail in error.errors())
            )
            return False
        if any(not animal.name for animal in config.animals):
            self.label_error.setText(
                "every animal card needs an animal; offline they come from the "
                f"animals in {get_database_path()}"
            )
            return False
        self.label_error.clear()
        self._config.save(config)
        return True

    def _on_cancel(self) -> None:
        self.reject()

    def _on_continue(self) -> None:
        if self._on_save():
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


def _database_animals(database: MXBIDatabase) -> tuple[AnimalOption, ...]:
    """The animals of ``db.json``, each with its RFID tags."""
    tags: dict[str, list[str]] = {}
    for tag, name in database.animals.items():
        tags.setdefault(name, []).append(tag)
    return tuple(AnimalOption("", name, tuple(t)) for name, t in tags.items())


def _configured_animals() -> tuple[AnimalOption, ...]:
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
    return tuple(
        AnimalOption(animal.id, animal.name, animal.rfid_tags)
        for animal in experiment.subjects
    )
