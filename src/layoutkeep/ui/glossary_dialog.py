"""Editing the glossary file from inside the application.

WHY THIS EXISTS: the glossary was a JSON file the user had to write by hand and point a setting at
- a feature that existed on the command line (`--glossary`) and, until the settings screen grew a
field for it, not at all from the application. A file picker is still not an editor: terms are
collected while reading a document, not while writing JSON, so the pairs belong in a table the
application can save back to the same file the run will read.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core import tunables
from layoutkeep.providers.glossary import Glossary, save_terms
from layoutkeep.ui.strings import UIStrings


class GlossaryDialog(QDialog):
    """A two-column table over the glossary JSON, saved where the run will look for it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.GLOSSARY_TITLE)
        self.resize(620, 460)
        self._path: Path | None = None

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(
            [UIStrings.GLOSSARY_SOURCE, UIStrings.GLOSSARY_TARGET]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setToolTip(UIStrings.GLOSSARY_TABLE_TIP)

        self._add_btn = QPushButton(UIStrings.GLOSSARY_ADD)
        self._remove_btn = QPushButton(UIStrings.GLOSSARY_REMOVE)
        self._load_btn = QPushButton(UIStrings.GLOSSARY_LOAD)
        self._save_btn = QPushButton(UIStrings.GLOSSARY_SAVE)
        self._export_btn = QPushButton(UIStrings.GLOSSARY_EXPORT)
        self._export_btn.setToolTip(UIStrings.GLOSSARY_EXPORT_TIP)
        self._export_btn.clicked.connect(self._export)
        self._suggest_btn = QPushButton(UIStrings.GLOSSARY_SUGGEST)
        self._suggest_btn.setToolTip(UIStrings.GLOSSARY_SUGGEST_TIP)
        self._suggest_btn.setEnabled(False)
        self._suggest_btn.clicked.connect(self._suggest)
        self._status = QLabel("")
        self._status.setProperty("class", "muted")
        self._status.setWordWrap(True)
        self._add_btn.clicked.connect(self._add_row)
        self._remove_btn.clicked.connect(self._remove_row)
        self._load_btn.clicked.connect(self._load)
        self._save_btn.clicked.connect(self._save_as)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        self._caption = QLabel(UIStrings.GLOSSARY_CAPTION)
        self._caption.setWordWrap(True)
        self._caption.setProperty("class", "muted")

        row = QHBoxLayout()
        row.addWidget(self._add_btn)
        row.addWidget(self._remove_btn)
        row.addWidget(self._suggest_btn)
        row.addStretch(1)
        row.addWidget(self._load_btn)
        row.addWidget(self._save_btn)
        row.addWidget(self._export_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._caption)
        layout.addWidget(self._table, 1)
        layout.addLayout(row)
        layout.addWidget(self._status)
        layout.addWidget(buttons)

        self._load_from_configured_path()

    # -- data --------------------------------------------------------------
    def terms(self) -> dict[str, str]:
        """The table as a glossary, skipping rows without a source term."""
        pairs: dict[str, str] = {}
        for index in range(self._table.rowCount()):
            source = self._cell(index, 0)
            target = self._cell(index, 1)
            if source:
                pairs[source] = target
        return pairs

    def set_terms(self, terms: dict[str, str]) -> None:
        self._table.setRowCount(0)
        for source, target in terms.items():
            self._append(source, target)

    def _cell(self, row: int, column: int) -> str:
        item = self._table.item(row, column)
        return (item.text() if item is not None else "").strip()

    def _append(self, source: str = "", target: str = "") -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(source))
        self._table.setItem(row, 1, QTableWidgetItem(target))

    # -- actions -----------------------------------------------------------
    def _add_row(self) -> None:
        self._append()
        self._table.setCurrentCell(self._table.rowCount() - 1, 0)
        self._table.editItem(self._table.item(self._table.rowCount() - 1, 0))

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)

    def set_document(self, path: str | Path | None) -> None:
        """The document to draw suggestions from (the job's input). Without one the button is off.

        Optional on purpose: the editor is also opened from the settings screen, where no job is
        in flight and there is nothing to read.
        """
        self._document = Path(path) if path else None
        self._suggest_btn.setEnabled(self._document is not None and self._document.exists())

    def _suggest(self) -> None:
        """Offer the terms the document repeats for preview; add the ones the person ticks.

        This is a list to review, never a glossary applied silently: the extraction is a frequency
        rule (core/terms.py), so the candidates are shown first (term_candidates_dialog.py), the
        ticked ones enter with an empty translation column, and nothing reaches a run until the
        user saves it. / Adaylar önce önizlenir; yalnız işaretlenenler boş hedefle eklenir.
        """
        if self._document is None or not self._document.exists():
            self._status.setText(UIStrings.GLOSSARY_SUGGEST_NONE)
            return
        self._status.setText(UIStrings.GLOSSARY_SUGGEST_READING)
        QApplication.processEvents()
        try:
            from layoutkeep.core.terms import suggest_from_document
            from layoutkeep.writers.converter import read_any_document

            document = read_any_document(self._document)
            limit = int(tunables.get("translation.suggest_limit"))
            found = suggest_from_document(document, limit=limit, exclude=set(self.terms()))
        except Exception as error:  # noqa: BLE001 - a suggestion that fails (a corrupt
            # file, an unsupported format) must not take the editing session down with it.
            self._status.setText(f"{type(error).__name__}: {error}")
            return
        existing = {source.strip().casefold() for source in self.terms()}
        fresh = [candidate for candidate in found if candidate.phrase.casefold() not in existing]
        if not fresh:
            self._status.setText(UIStrings.GLOSSARY_SUGGEST_EMPTY)
            return
        from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

        preview = TermCandidatesDialog(fresh, self)
        if not preview.exec():
            self._status.setText("")
            return
        chosen = preview.chosen()
        for phrase in chosen:
            self._append(phrase, "")
        self._status.setText(UIStrings.GLOSSARY_SUGGEST_ADDED.format(count=len(chosen)))

    def _load(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, UIStrings.GLOSSARY_LOAD, str(self._path or ""), UIStrings.TWEAKS_GLOSSARY_FILTER
        )
        if not chosen:
            return
        try:
            # The run's own reader: JSON, CSV or TSV, as the file filter promises.
            # Çalışmanın kendi okuyucusu: filtrenin söz verdiği JSON, CSV veya TSV.
            terms = Glossary.load(chosen).terms
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, UIStrings.GLOSSARY_TITLE, f"{UIStrings.GLOSSARY_BAD_FILE}\n{exc}")
            return
        self._path = Path(chosen)
        self.set_terms(terms)

    def _export(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self, UIStrings.GLOSSARY_EXPORT, str((self._path or Path("glossary")).with_suffix(".csv")),
            UIStrings.GLOSSARY_EXPORT_FILTER,
        )
        if chosen:
            self.export_to(Path(chosen))

    def export_to(self, path: Path) -> Path | None:
        """Write a copy of the table to `path` (CSV, TSV or JSON by its suffix).

        A copy on purpose: the run keeps reading the file the setting points at, so exporting for a
        spreadsheet never moves the glossary a job uses. / Kopya yazar; ayardaki dosya değişmez.
        """
        try:
            save_terms(path, self.terms())
        except OSError as exc:
            QMessageBox.warning(self, UIStrings.GLOSSARY_TITLE, str(exc))
            return None
        self._status.setText(UIStrings.GLOSSARY_EXPORTED.format(count=len(self.terms()), path=path))
        return path

    def _save_as(self) -> Path | None:
        chosen, _ = QFileDialog.getSaveFileName(
            self, UIStrings.GLOSSARY_SAVE, str(self._path or "glossary.json"),
            UIStrings.TWEAKS_GLOSSARY_FILTER,
        )
        if not chosen:
            return None
        self._path = Path(chosen)
        return self._write()

    def _write(self) -> Path | None:
        if self._path is None:
            return None
        try:
            save_terms(self._path, self.terms())
        except OSError as exc:
            QMessageBox.warning(self, UIStrings.GLOSSARY_TITLE, str(exc))
            return None
        return self._path

    def _accept(self) -> None:
        """Save to the file the setting points at, and point the setting at it.

        The setting is the contract with the run: a glossary saved somewhere the next job will not
        look is a file, not a glossary.
        """
        configured = str(tunables.get("translation.glossary_path") or "").strip()
        if self._path is None and configured:
            self._path = Path(configured)
        if self._path is None:
            if not self.terms():
                self.accept()
                return
            if self._save_as() is None:
                return
        elif self._write() is None:
            return
        if self._path is not None:
            tunables.set_value("translation.glossary_path", str(self._path))
            tunables.save()
        self.accept()

    def _load_from_configured_path(self) -> None:
        configured = str(tunables.get("translation.glossary_path") or "").strip()
        if not configured or not Path(configured).exists():
            return
        self._path = Path(configured)
        try:
            self.set_terms(Glossary.load(self._path).terms)
        except (OSError, ValueError, TypeError):
            return
