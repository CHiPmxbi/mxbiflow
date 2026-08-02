from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.config_store import ConfigStore
from ..core.path import (
    get_config_session_path,
    get_mxbi_panel_config_path,
    get_options_session_path,
)
from ..models.panel import MXBIPanelConfig
from ..models.session import Options, SessionConfig
from ..scene import SceneManager
from .components.countdown import AutoAcceptCountdown
from .components.experiment_groups import (
    ExperimentAnimalsGroup,
    ExperimentConfigGroup,
    ExperimentSceneGroup,
)


class ExperimentPanel(QMainWindow):
    accepted = Signal()
    rejected = Signal()

    def __init__(self, scene_manager: SceneManager) -> None:
        super().__init__()
        self._accepted = False
        self._config = ConfigStore(get_config_session_path(), SessionConfig)
        self._options = ConfigStore(get_options_session_path(), Options)
        self._stage_level_tables = scene_manager.stage_level_tables

        self.setWindowTitle("Experiment Panel")

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout_main = QVBoxLayout(self)
        central_widget.setLayout(layout_main)

        self.group_config = ExperimentConfigGroup(
            self, self._options.value.experimenter
        )
        layout_main.addWidget(self.group_config)

        self.group_scene = ExperimentSceneGroup(
            self,
            stages=list(self._stage_level_tables.keys()),
            animals=self._fallback_animal_options(),
        )
        layout_main.addWidget(self.group_scene)

        self.group_animals = ExperimentAnimalsGroup(
            self,
            animals=self._options.value.animals,
            stage_level_tables=self._stage_level_tables,
        )
        layout_main.addWidget(self.group_animals)

        self.combo_experimenter = self.group_config.combo_experimenter
        self.combo_reward_type = self.group_config.combo_reward_type
        self.line_notes = self.group_config.line_notes

        layout_buttons = QGridLayout(self)
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

    def result(self) -> SessionConfig:
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

    def _fallback_animal_options(self) -> list[str]:
        names = list(self._options.value.animals.values())
        names.extend(animal.name for animal in self._config.value.animals)
        return list(dict.fromkeys(name for name in names if name))

    def _on_save(self) -> None:
        self._config.save(self.result())

    def _on_cancel(self) -> None:
        self.close()

    def _on_continue(self) -> None:
        self._on_save()
        self._accepted = True
        self.close()
        self.accepted.emit()

    def _start_auto_accept_countdown(self) -> None:
        panel_config = ConfigStore(
            get_mxbi_panel_config_path(), MXBIPanelConfig
        ).value
        self._countdown.start(panel_config.auto_accept_timeout_seconds)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._start_auto_accept_countdown()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._countdown.stop()
        super().closeEvent(event)
        if event.isAccepted() and not self._accepted:
            self.rejected.emit()
