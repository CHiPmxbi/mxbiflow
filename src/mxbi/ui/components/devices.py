from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Generic, TypeVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QMenu,
    QMessageBox,
    QWidget,
)

from .device_card.device_card import DeviceCard

from .dialog.add_devices_dialog import AddDeviceDialog
from ...models.mxbi import RewarderModel, DetectorModel

T = TypeVar("T", RewarderModel, DetectorModel)


class Devices(QGroupBox, Generic[T]):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        *,
        action_label: str,
        device_types: Sequence[str],
        dialog_title: str,
        label: str,
        card_factories: Mapping[str, type[QWidget]],
        columns: int = 2,
    ):
        super().__init__(title, parent)

        self._action_label = action_label
        self._device_types = list(device_types)
        self._dialog_title = dialog_title
        self._label = label
        self._card_factories = dict(card_factories)
        self._columns = max(1, int(columns))

        self._cards: list[DeviceCard[T]] = []

        self._build_ui()
        self._bind_events()

    @property
    def cards(self) -> list[DeviceCard[T]]:
        return list(self._cards)

    def results(self) -> list[T]:
        return [card.result for card in self._cards]

    def load_models(self, models: Sequence[T]) -> None:
        for model in models:
            self.add_model(model)

    def add_model(self, model: T) -> None:
        try:
            device_type = model.device_type
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Unsupported device",
                f"Failed to determine device type ({exc!s})",
            )
            return
        if device_type is None:
            QMessageBox.warning(
                self,
                "Unsupported device",
                "Missing device type",
            )
            return

        self._add_device_card(str(device_type), model=model)

    # -----------------------------
    # UI / Events
    # -----------------------------

    def _build_ui(self) -> None:
        layout = QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for col in range(self._columns):
            layout.setColumnStretch(col, 1)
        self.setLayout(layout)

    def _bind_events(self) -> None:
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

    def _open_menu(self, position) -> None:
        menu = QMenu(self)
        action = menu.addAction(self._action_label)
        action.triggered.connect(lambda _checked=False: self._on_add_clicked())
        menu.exec(self.mapToGlobal(position))

    def _on_add_clicked(self) -> None:
        dialog = AddDeviceDialog(
            self,
            device_types=self._device_types,
            title=self._dialog_title,
            label=self._label,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._add_device_card(dialog.device_type, model=None)

    # -----------------------------
    # Cards / Layout
    # -----------------------------

    def _add_device_card(self, device_type: str, *, model: T | None) -> None:
        card_factory = self._card_factories.get(device_type)
        if card_factory is None:
            QMessageBox.warning(
                self,
                "Unsupported device",
                f"Unsupported device type: {device_type}",
            )
            return

        card = card_factory()
        if isinstance(card, DeviceCard):
            if model is not None:
                card.load_config(model)
            card.remove_requested.connect(lambda c=card: self._on_remove_requested(c))
            self._cards.append(card)

        self._mount(card)

    def _on_remove_requested(self, card: DeviceCard[T]) -> None:
        self._remove_card(card)

    def _remove_card(self, card: DeviceCard[T]) -> None:
        layout = self.layout()
        if isinstance(layout, QGridLayout):
            layout.removeWidget(card)
        card.setParent(None)
        card.deleteLater()

        self._reflow_cards()

    def _reflow_cards(self) -> None:
        layout = self.layout()
        if not isinstance(layout, QGridLayout):
            return

        cards: list[DeviceCard[T]] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, DeviceCard):
                cards.append(widget)

        while layout.count() > 0:
            layout.takeAt(0)

        self._cards = cards
        for index, widget in enumerate(cards):
            row, col = divmod(index, self._columns)
            layout.addWidget(widget, row, col)

    def _mount(self, widget: QWidget) -> None:
        layout = self.layout()
        if layout is None:
            return

        if isinstance(layout, QGridLayout):
            index = layout.count()
            row, col = divmod(index, self._columns)
            layout.addWidget(widget, row, col)
            return

        layout.addWidget(widget)
