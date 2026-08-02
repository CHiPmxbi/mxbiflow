from typing import NamedTuple

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
    QWidget,
)

from ...models.animal import AnimalConfig
from ...models.session import RewardEnum, SessionConfig
from .animal import AnimalCard


class ExperimentConfigGroup(QGroupBox):
    def __init__(self, parent: QWidget | None, experimenters: list[str]) -> None:
        super().__init__("Config", parent)

        self._experimenters = experimenters
        self._reward_types = list(RewardEnum)

        layout = QGridLayout(self)
        self.setLayout(layout)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)

        layout.addWidget(QLabel("experimenter", self), 0, 0)
        self.combo_experimenter = QComboBox(self)
        self.combo_experimenter.addItems(experimenters)
        layout.addWidget(self.combo_experimenter, 0, 1)

        layout.addWidget(QLabel("reward type", self), 0, 2)
        self.combo_reward_type = QComboBox(self)
        self.combo_reward_type.addItems(list(RewardEnum))
        layout.addWidget(self.combo_reward_type, 0, 3)

        layout.addWidget(QLabel("hide cursor", self), 1, 0)
        self.check_hide_cursor = QCheckBox(self)
        layout.addWidget(self.check_hide_cursor, 1, 1)

        layout.addWidget(QLabel("fullscreen", self), 1, 2)
        self.check_fullscreen = QCheckBox(self)
        layout.addWidget(self.check_fullscreen, 1, 3)

        layout.addWidget(QLabel("send email", self), 2, 0)
        self.check_send_email = QCheckBox(self)
        layout.addWidget(self.check_send_email, 2, 1)

        layout.addWidget(QLabel("sync data", self), 2, 2)
        self.check_sync_data = QCheckBox(self)
        layout.addWidget(self.check_sync_data, 2, 3)

        layout.addWidget(QLabel("notes", self), 3, 0)
        self.line_notes = QLineEdit(self)
        self.line_notes.setPlaceholderText("Notes")
        layout.addWidget(self.line_notes, 3, 1, 1, 3)

        layout.addWidget(QLabel("auto accept (s)", self), 4, 0)
        self.spin_auto_accept = QSpinBox(self)
        self.spin_auto_accept.setRange(0, 3600)
        self.spin_auto_accept.setSpecialValueText("Disabled")
        layout.addWidget(self.spin_auto_accept, 4, 1)

    def load_config(self, config: SessionConfig) -> None:
        if config.experimenter in self._experimenters:
            self.combo_experimenter.setCurrentText(config.experimenter)
        else:
            self.combo_experimenter.setCurrentIndex(0)

        if config.reward_type in self._reward_types:
            self.combo_reward_type.setCurrentText(config.reward_type.value)
        else:
            self.combo_reward_type.setCurrentIndex(0)

        self.check_hide_cursor.setChecked(config.hide_cursor)
        self.check_fullscreen.setChecked(config.fullscreen)
        self.spin_auto_accept.setValue(config.auto_accept_timeout_seconds)
        self.check_send_email.setChecked(config.send_email)
        self.check_sync_data.setChecked(config.sync_data)

    def result(self) -> SessionConfig:
        return SessionConfig(
            experimenter=self.combo_experimenter.currentText(),
            reward_type=RewardEnum(self.combo_reward_type.currentText()),
            note=self.line_notes.text(),
            hide_cursor=self.check_hide_cursor.isChecked(),
            fullscreen=self.check_fullscreen.isChecked(),
            auto_accept_timeout_seconds=self.spin_auto_accept.value(),
            send_email=self.check_send_email.isChecked(),
            sync_data=self.check_sync_data.isChecked(),
        )


class SceneSelection(NamedTuple):
    default_scene: str
    unknown_animal_as: str
    fault_fallback: str


class ExperimentSceneGroup(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        stages: list[str],
        animals: list[str],
    ) -> None:
        super().__init__("Scene", parent)

        layout = QFormLayout(self)
        self.setLayout(layout)

        label_default = QLabel("default scene", self)
        self.combo_default_scene = QComboBox(self)
        self.combo_default_scene.addItems(stages)
        layout.addRow(label_default, self.combo_default_scene)

        label_unknown_animal = QLabel("unknown animal as", self)
        self.combo_unknown_animal_as = QComboBox(self)
        self.combo_unknown_animal_as.addItems(animals)
        layout.addRow(
            label_unknown_animal,
            self.combo_unknown_animal_as,
        )

        label_fault = QLabel("fault fallback", self)
        self.combo_fault_fallback = QComboBox(self)
        self.combo_fault_fallback.addItems(stages)
        layout.addRow(label_fault, self.combo_fault_fallback)

    def load_config(self, config: SessionConfig) -> None:
        if config.default_scene:
            self.combo_default_scene.setCurrentText(config.default_scene)
        if config.unknown_animal_as:
            if self.combo_unknown_animal_as.findText(config.unknown_animal_as) < 0:
                self.combo_unknown_animal_as.addItem(config.unknown_animal_as)
            self.combo_unknown_animal_as.setCurrentText(config.unknown_animal_as)
        if config.fault_fallback:
            self.combo_fault_fallback.setCurrentText(config.fault_fallback)

    def result(self) -> SceneSelection:
        return SceneSelection(
            default_scene=self.combo_default_scene.currentText(),
            unknown_animal_as=self.combo_unknown_animal_as.currentText(),
            fault_fallback=self.combo_fault_fallback.currentText(),
        )


class ExperimentAnimalsGroup(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        animals: dict[str, str],
        stage_level_tables: dict[str, dict[str, list[int]]],
    ) -> None:
        super().__init__("Animals", parent)

        self._animals = animals
        self._stage_level_tables = stage_level_tables
        self.layout_animals = QGridLayout(self)
        self.setLayout(self.layout_animals)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        action = menu.addAction("Add animal")
        action.triggered.connect(lambda _checked=False: self._on_add_animal())
        menu.exec(self.mapToGlobal(pos))

    def _on_add_animal(self) -> None:
        animal_card = AnimalCard(self, self._animals, self._stage_level_tables)
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

    def load_config(self, config: SessionConfig) -> None:
        for animal_configs in config.animals:
            animal_card = AnimalCard(self, self._animals, self._stage_level_tables)
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
