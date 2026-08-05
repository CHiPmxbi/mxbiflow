from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.context import get_mxbiflow
from ..infra.post_processing import SessionSummary, summarize
from .application import require_application
from .components.countdown import AutoAcceptCountdown

_AUTO_ACCEPT_SECONDS = 30
_VISIBLE_TABLE_ROWS = 2


def run_session_summary() -> bool:
    """Show the current session summary and return whether upload should continue."""
    _application = require_application()
    return (
        SessionSummaryPanel(summarize(get_mxbiflow().session)).exec()
        == QDialog.DialogCode.Accepted
    )


class SessionSummaryPanel(QDialog):
    def __init__(self, summary: SessionSummary) -> None:
        super().__init__()
        self._summary = summary

        self.setWindowTitle("Session Summary")
        self.setModal(True)
        self.setMinimumSize(760, 480)
        self.resize(900, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(self._build_session_group())
        layout.addWidget(self._build_animals_group())
        layout.addWidget(self._build_stages_group())
        layout.addLayout(self._build_buttons())

    def _build_session_group(self) -> QGroupBox:
        group = QGroupBox("Session", self)
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        rows = (
            (
                ("Session ID", str(self._summary.session_id)),
                ("Start Time", _format_timestamp(self._summary.start_at)),
            ),
            (
                ("End Time", _format_timestamp(self._summary.end_at)),
                ("Duration", _format_duration(self._summary.duration_seconds)),
            ),
            (
                ("Experimenter", self._summary.experimenter or "N/A"),
                ("Reward Type", self._summary.reward_type or "N/A"),
            ),
            (
                ("Total Animals", str(self._summary.total_animals)),
                ("Note", self._summary.note or "N/A"),
            ),
        )
        for row_index, row in enumerate(rows):
            for pair_index, (label_text, value) in enumerate(row):
                column = pair_index * 2
                grid.addWidget(QLabel(label_text, group), row_index, column)
                value_label = QLabel(value, group)
                value_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                value_label.setWordWrap(label_text == "Note")
                grid.addWidget(value_label, row_index, column + 1)

        return group

    def _build_animals_group(self) -> QGroupBox:
        group = QGroupBox("Animals", self)
        layout = QVBoxLayout(group)
        headers = (
            "Name",
            "RFID ID",
            "Total Trials",
            "Animal Sessions",
            "Duration",
        )
        rows = [
            (
                animal.name,
                animal.rfid_id or "N/A",
                str(animal.total_trials),
                str(animal.animal_sessions),
                _format_duration(animal.total_duration_seconds),
            )
            for animal in self._summary.animals
        ]
        self.animals_table = _build_read_only_table(headers, rows, group)
        self.animals_table.setAccessibleName("Animal session summary")
        layout.addWidget(self.animals_table)
        return group

    def _build_stages_group(self) -> QGroupBox:
        group = QGroupBox("Stages", self)
        layout = QVBoxLayout(group)
        headers = ("Animal", "Stage", "Trials", "Initial Level", "Final Level")
        rows = [
            (
                animal.name,
                stage.name,
                str(stage.trials),
                str(stage.initial_level),
                str(stage.final_level),
            )
            for animal in self._summary.animals
            for stage in animal.stages
        ]
        self.stages_table = _build_read_only_table(headers, rows, group)
        self.stages_table.setAccessibleName("Stage session summary")
        layout.addWidget(self.stages_table)
        return group

    def _build_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self._countdown = AutoAcceptCountdown(self)
        self._countdown.timeout.connect(self.accept)
        layout.addWidget(self._countdown)
        layout.addStretch()

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

        continue_button = QPushButton("Continue", self)
        continue_button.clicked.connect(self.accept)
        layout.addWidget(continue_button)
        return layout

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._countdown.start(_AUTO_ACCEPT_SECONDS)

    def done(self, result: int) -> None:
        self._countdown.stop()
        super().done(result)


def _build_read_only_table(
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    parent: QGroupBox,
) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            table.setItem(row_index, column_index, QTableWidgetItem(value))

    visible_rows = min(max(len(rows), 1), _VISIBLE_TABLE_ROWS)
    table_height = (
        table.horizontalHeader().sizeHint().height()
        + visible_rows * table.verticalHeader().defaultSectionSize()
        + table.frameWidth() * 2
    )
    table.setFixedHeight(table_height)

    return table


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
