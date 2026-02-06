from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config_store import ConfigStore
from ..models.session import Options, SessionConfig
from .components.experiment_groups import ExperimentAnimalsGroup, ExperimentConfigGroup


class ExperimentPanel(QMainWindow):
    accepted = Signal()

    def __init__(self, session_config_path: Path, options_path: Path):
        super().__init__()
        self._config = ConfigStore(session_config_path, SessionConfig)
        self._options = ConfigStore(options_path, Options)

        self.setWindowTitle("Experiment Panel")

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout_main = QVBoxLayout(self)
        central_widget.setLayout(layout_main)

        self.group_config = ExperimentConfigGroup(
            self, self._options.value.experimenter
        )
        layout_main.addWidget(self.group_config)

        self.group_animals = ExperimentAnimalsGroup(
            self, animals=self._options.value.animals, options=self._options.value
        )
        layout_main.addWidget(self.group_animals)

        self.combo_experimenter = self.group_config.combo_experimenter
        self.combo_reward_type = self.group_config.combo_reward_type
        self.line_notes = self.group_config.line_notes

        layout_buttons = QHBoxLayout(self)
        layout_main.addLayout(layout_buttons)
        self._button_cancle = QPushButton("Cancel", self)
        self._button_save = QPushButton("Save", self)
        self._button_continue = QPushButton("Continue", self)
        layout_buttons.addWidget(self._button_cancle)
        layout_buttons.addWidget(self._button_save)
        layout_buttons.addWidget(self._button_continue)

        self._bind_signals()
        self.load_config()

    def _bind_signals(self):
        self._button_cancle.clicked.connect(self._on_cancle)
        self._button_save.clicked.connect(self._on_save)
        self._button_continue.clicked.connect(self._on_continue)

    def load_config(self):
        self.group_config.load_config(self._config.value)
        self.group_animals.load_config(self._config.value)

    def result(self) -> SessionConfig:
        session_config = self.group_config.result()
        session_config.animals = self.group_animals.result()
        return session_config

    def _on_save(self):
        self._config.save(self.result())

    def _on_cancle(self):
        self.close()

    def _on_continue(self):
        self._on_save()
        self.close()
        self.accepted.emit()
