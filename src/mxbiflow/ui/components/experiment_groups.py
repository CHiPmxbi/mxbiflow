from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
)
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt

from .animal import AnimalCard
from ...models.session import SessionConfig, RewardEnum
from ...models.animal import AnimalConfig


class ExperimentConfigGroup(QGroupBox):
    def __init__(self, parent, experimenters: list[str]):
        super().__init__("Config", parent)

        layout = QFormLayout(self)
        self.setLayout(layout)

        lable_session_id = QLabel("session id", self)
        self.line_session_id = QLineEdit(self)
        self.line_session_id.setValidator(QIntValidator(self))
        layout.addRow(lable_session_id, self.line_session_id)

        lable_experimenter = QLabel("experimenter", self)
        self.combo_experimenter = QComboBox(self)
        self.combo_experimenter.addItems(experimenters)
        layout.addRow(lable_experimenter, self.combo_experimenter)

        lable_reward_type = QLabel("reward type", self)
        self.combo_reward_type = QComboBox(self)
        self.combo_reward_type.addItems(list(RewardEnum))
        layout.addRow(lable_reward_type, self.combo_reward_type)

        lable_notes = QLabel("notes", self)
        self.line_notes = QLineEdit(self)
        self.line_notes.setPlaceholderText("Notes")
        layout.addRow(lable_notes, self.line_notes)

    def load_config(self, config: SessionConfig):
        self.combo_experimenter.setEditText(config.experimenter)
        self.combo_reward_type.setEditText(config.reward_type)

    def result(self) -> SessionConfig:
        return SessionConfig(
            experimenter=self.combo_experimenter.currentText(),
            reward_type=RewardEnum(self.combo_reward_type.currentText()),
        )


class ExperimentAnimalsGroup(QGroupBox):
    def __init__(self, parent=None, *, animals: dict[str, str]):
        super().__init__("Animals", parent)

        self._animals = animals
        self.layout_animals = QGridLayout(self)
        self.setLayout(self.layout_animals)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        action = menu.addAction("Add animal")
        action.triggered.connect(lambda _checked=False: self._on_add_animal())
        menu.exec(self.mapToGlobal(pos))

    def _on_add_animal(self):
        animal_card = AnimalCard(self, self._animals)
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
            item = self.layout_animals.itemAt(i)
            if item:
                widget = item.widget()
                if isinstance(widget, AnimalCard):
                    cards.append(widget)

        while self.layout_animals.count() > 0:
            self.layout_animals.takeAt(0)

        for card in cards:
            self._add_animal_card(card)

    def load_config(self, config: SessionConfig):
        for animal_configs in config.animals:
            animal_card = AnimalCard(self, self._animals)
            animal_card.load_config(animal_configs)
            animal_card.remove_requested.connect(
                lambda _card=animal_card: self._on_remove_animal(_card)
            )
            self._add_animal_card(animal_card)

    def result(self) -> list[AnimalConfig]:
        results: list[AnimalConfig] = []
        for i in range(self.layout_animals.count()):
            item = self.layout_animals.itemAt(i)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, AnimalCard):
                results.append(widget.result)
        return results
