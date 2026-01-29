from PySide6.QtWidgets import QLabel, QFormLayout, QComboBox, QMenu
from PySide6.QtCore import Qt, Signal

from .card import CardFrame


class AnimalCard(CardFrame):
    remove_requested = Signal()

    def __init__(self, parent, animals: dict[str, str]):
        super().__init__(parent=parent, object_name="card")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        label_animal_name = QLabel("animal", self)
        self.combo_animal_name = QComboBox(self)
        self.combo_animal_name.addItems([i for i in animals.values()])
        layout.addRow(label_animal_name, self.combo_animal_name)

        lable_animal_if = QLabel("id", self)
        self.combo_animal_id = QComboBox(self)
        self.combo_animal_id.addItems([i for i in animals.keys()])
        layout.addRow(lable_animal_if, self.combo_animal_id)

        label_stage = QLabel("stage", self)
        self.combo_stage = QComboBox(self)
        layout.addRow(label_stage, self.combo_stage)

        label_level = QLabel("level", self)
        self.combo_level = QComboBox(self)
        layout.addRow(label_level, self.combo_level)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        action = menu.addAction("Remove")
        action.triggered.connect(lambda _checked=False: self.remove_requested.emit())
        menu.exec(self.mapToGlobal(pos))
