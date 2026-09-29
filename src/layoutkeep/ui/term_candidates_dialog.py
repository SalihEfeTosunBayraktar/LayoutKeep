"""Preview of the term candidates a document offers, before any of them enters the glossary.

Belgeden çıkan terim adaylarının önizlemesi: sözlüğe hangilerinin gireceğini kullanıcı seçer.

WHY THIS EXISTS: "Suggest from document" appended every candidate straight to the glossary table,
so a person had to delete the grammar and boilerplate the frequency rule let through, one row at a
time, among the rows they had written themselves. The candidates are a proposal (core/terms.py says
so in its own docstring), and a proposal is read before it is accepted: each one is shown with how
often the document uses it, ticked, and only the ticked ones are added.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.strings import UIStrings


class TermCandidatesDialog(QDialog):
    """A ticked list of candidates with their counts; `chosen()` is what the person kept."""

    def __init__(self, candidates: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.CANDIDATES_TITLE)
        self.resize(520, 480)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels([UIStrings.CANDIDATES_TERM, UIStrings.CANDIDATES_COUNT])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for candidate in candidates:
            self._append(candidate.phrase, candidate.count)

        caption = QLabel(UIStrings.CANDIDATES_CAPTION)
        caption.setWordWrap(True)
        caption.setProperty("class", "muted")

        select_all = QPushButton(UIStrings.CANDIDATES_ALL)
        select_all.clicked.connect(lambda: self._tick_all(True))
        select_none = QPushButton(UIStrings.CANDIDATES_NONE)
        select_none.clicked.connect(lambda: self._tick_all(False))
        row = QHBoxLayout()
        row.addWidget(select_all)
        row.addWidget(select_none)
        row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(UIStrings.CANDIDATES_ADD)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(caption)
        layout.addWidget(self._table, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def _append(self, phrase: str, count: int) -> None:
        # Aday satırı: işaretli terim + kullanım sayısı / Candidate row: ticked term + its count
        index = self._table.rowCount()
        self._table.insertRow(index)
        term = QTableWidgetItem(phrase)
        term.setFlags(term.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        term.setCheckState(Qt.CheckState.Checked)
        self._table.setItem(index, 0, term)
        times = QTableWidgetItem(str(count))
        times.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(index, 1, times)

    def _tick_all(self, ticked: bool) -> None:
        state = Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
        for index in range(self._table.rowCount()):
            self._table.item(index, 0).setCheckState(state)

    def set_ticked(self, phrase: str, ticked: bool) -> None:
        """Tick or untick one candidate by its text (what a click on its box does)."""
        state = Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
        for index in range(self._table.rowCount()):
            if self._table.item(index, 0).text() == phrase:
                self._table.item(index, 0).setCheckState(state)

    def chosen(self) -> list[str]:
        """The ticked candidates, in the order they were offered."""
        return [
            self._table.item(index, 0).text()
            for index in range(self._table.rowCount())
            if self._table.item(index, 0).checkState() == Qt.CheckState.Checked
        ]
