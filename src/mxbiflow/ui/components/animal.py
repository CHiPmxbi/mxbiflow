from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QWidget,
)

from ...models.animal import AnimalConfig
from .card import CardFrame

# stage_name -> {animal_name -> [level_ids]}
StageLevelTables = dict[str, dict[str, list[int]]]


class AnimalCard(CardFrame):
    remove_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None,
        animals: dict[str, str],
        stage_level_tables: StageLevelTables,
    ) -> None:
        super().__init__(parent=parent, object_name="card")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._stage_level_tables = stage_level_tables

        items = list(animals.items())
        self._animal_ids = [animal_id for animal_id, _name in items]
        self._animal_names = [name for _animal_id, name in items]

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        label_animal_name = QLabel("animal", self)
        self.combo_animal_name = QComboBox(self)
        self.combo_animal_name.addItems(self._animal_names)
        self.combo_animal_name.currentIndexChanged.connect(self._on_animal_changed)
        layout.addRow(label_animal_name, self.combo_animal_name)

        lable_animal_id = QLabel("id", self)
        self.line_animal_id = QLineEdit(self)
        self.line_animal_id.setReadOnly(True)
        self.line_animal_id.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addRow(lable_animal_id, self.line_animal_id)

        label_stage = QLabel("stage", self)
        self.combo_stage = QComboBox(self)
        self.combo_stage.addItems(list(stage_level_tables.keys()))
        self.combo_stage.setCurrentText("idle")
        self.combo_stage.currentTextChanged.connect(self._on_stage_changed)
        layout.addRow(label_stage, self.combo_stage)

        label_level = QLabel("level", self)
        self.combo_level = QComboBox(self)
        layout.addRow(label_level, self.combo_level)

        self._sync_animal_id()
        self._sync_levels()

    def _on_animal_changed(self, _index: int) -> None:
        self._sync_animal_id()
        self._sync_levels()

    def _on_stage_changed(self, _text: str) -> None:
        self._sync_levels()

    def _sync_levels(self) -> None:
        stage = self.combo_stage.currentText()
        animal_name = self.combo_animal_name.currentText()

        level_table = self._stage_level_tables.get(stage, {})
        levels = level_table.get(animal_name) or level_table.get("default", [])

        self.combo_level.clear()
        if levels:
            self.combo_level.addItems([str(lv) for lv in levels])
            self.combo_level.setCurrentIndex(0)
            self.combo_level.setEnabled(True)
        else:
            self.combo_level.setEnabled(False)

    def _sync_animal_id(self) -> None:
        index = self.combo_animal_name.currentIndex()
        if index < 0 or index >= len(self._animal_ids):
            self.line_animal_id.setText("")
            return
        self.line_animal_id.setText(self._animal_ids[index])

    def animal_id(self) -> str:
        return self.line_animal_id.text()

    def animal_name(self) -> str:
        return self.combo_animal_name.currentText()

    def _on_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        action = menu.addAction("Remove")
        action.triggered.connect(lambda _checked=False: self.remove_requested.emit())
        menu.exec(self.mapToGlobal(pos))

    def load_config(self, config: AnimalConfig) -> None:
        self.combo_animal_name.setCurrentText(config.name)
        self.combo_stage.setCurrentText(config.stage)
        self.combo_level.setCurrentText(str(config.level))

    @property
    def result(self) -> AnimalConfig:
        return AnimalConfig(
            rfid_id=self.animal_id(),
            name=self.animal_name(),
            stage=self.combo_stage.currentText(),
            level=int(self.combo_level.currentText())
            if self.combo_level.currentText()
            else 0,
        )
