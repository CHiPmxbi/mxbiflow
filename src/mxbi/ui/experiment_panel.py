from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QGroupBox,
    QMenu,
)

from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Signal, Qt
from ..models.session import SessionConfig, Options
from .components.animal import AnimalCard
from ..config import Configure
from ..path import SESSION_CONFIG_PATH, OPTIONS_PATH


class ExperimentPanel(QMainWindow):
    accepted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = Configure(SESSION_CONFIG_PATH, SessionConfig)
        self._options = Configure(OPTIONS_PATH, Options)

        self.setWindowTitle("Experiment Panel")

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout_main = QVBoxLayout(self)
        central_widget.setLayout(layout_main)

        layout_config_group = QGroupBox("Config", self)
        layout_main.addWidget(layout_config_group)

        layout_config = QFormLayout(self)
        layout_config_group.setLayout(layout_config)

        lable_session_id = QLabel("session id", self)
        self.line_session_id = QLineEdit(self)
        int_validator = QIntValidator(self)
        self.line_session_id.setValidator(int_validator)
        layout_config.addRow(lable_session_id, self.line_session_id)

        lable_experimenter = QLabel("experimenter", self)
        self.combo_experimenter = QComboBox()
        self.combo_experimenter.setEditable(True)
        layout_config.addRow(lable_experimenter, self.combo_experimenter)

        lable_reward_type = QLabel("reward type", self)
        self.combo_reward_type = QComboBox()
        self.combo_reward_type.setEditable(True)
        layout_config.addRow(lable_reward_type, self.combo_reward_type)

        lable_notes = QLabel("notes", self)
        self.line_notes = QLineEdit(self)
        self.line_notes.setPlaceholderText("Notes")
        layout_config.addRow(lable_notes, self.line_notes)

        self.group_animals = QGroupBox("Animals", self)
        self.layout_animals = QGridLayout(self)
        self.group_animals.setLayout(self.layout_animals)
        layout_main.addWidget(self.group_animals)

        layout_buttons = QHBoxLayout(self)
        layout_main.addLayout(layout_buttons)
        self._button_cancle = QPushButton("Cancel", self)
        self._button_save = QPushButton("Save", self)
        self._button_continue = QPushButton("Continue", self)
        layout_buttons.addWidget(self._button_cancle)
        layout_buttons.addWidget(self._button_save)
        layout_buttons.addWidget(self._button_continue)

        self._bind_signals()

    def _bind_context_menu(self):
        self.group_animals.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.group_animals.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        action = menu.addAction("Add animal")
        action.triggered.connect(lambda _checked=False: self._on_add_animal())
        menu.exec(self.group_animals.mapToGlobal(pos))

    def _on_add_animal(self):
        animal_card = AnimalCard(self, self._options.value.animals)
        animal_card.remove_requested.connect(
            lambda _card=animal_card: self._on_remove_animal(_card)
        )
        self._add_animal_card(animal_card)

    def _add_animal_card(self, animal_card: AnimalCard) -> None:
        index = self.layout_animals.count()
        row = index // 4
        col = index % 4
        self.layout_animals.addWidget(animal_card, row, col)

    def _on_remove_animal(self, animal_card: AnimalCard) -> None:
        self.layout_animals.removeWidget(animal_card)
        animal_card.setParent(None)
        animal_card.deleteLater()
        self._reflow_animal_cards()

    def _reflow_animal_cards(self) -> None:
        cards: list[AnimalCard] = []
        for i in range(self.layout_animals.count()):
            i = self.layout_animals.itemAt(i)
            if i:
                widget = i.widget()

                if isinstance(widget, AnimalCard):
                    cards.append(widget)

        while self.layout_animals.count() > 0:
            self.layout_animals.takeAt(0)

        for card in cards:
            self._add_animal_card(card)

    def _bind_signals(self):
        self._bind_context_menu()
        self._button_continue.clicked.connect(self._on_continue)

    def _on_continue(self):
        self.close()
        self.accepted.emit()


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    experiment_panel = ExperimentPanel()
    experiment_panel.show()
    sys.exit(app.exec())
