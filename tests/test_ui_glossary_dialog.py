"""The glossary editor: a table over the JSON file the run reads.

The feature exists to be *used*: terms are noticed while reading a document, so entering them must
not mean opening a text editor and getting the JSON exactly right.
"""

from __future__ import annotations

import json

from layoutkeep.core import tunables
from layoutkeep.ui.glossary_dialog import GlossaryDialog
from layoutkeep.ui.strings import UIStrings


def _dialog(qtbot) -> GlossaryDialog:
    dialog = GlossaryDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_rows_become_a_glossary_and_blank_sources_are_ignored(qtbot):
    dialog = _dialog(qtbot)

    dialog.set_terms({"Annual Report": "Yıllık Rapor", "": "boş"})

    assert dialog.terms() == {"Annual Report": "Yıllık Rapor"}


def test_add_and_remove_rows(qtbot):
    dialog = _dialog(qtbot)
    dialog.set_terms({})

    dialog._add_row()
    dialog._table.item(0, 0).setText("Report")
    dialog._table.item(0, 1).setText("Rapor")
    dialog._add_row()
    dialog._table.item(1, 0).setText("Draft")
    dialog._table.item(1, 1).setText("Taslak")
    assert dialog.terms() == {"Report": "Rapor", "Draft": "Taslak"}

    dialog._table.setCurrentCell(0, 0)
    dialog._remove_row()

    assert dialog.terms() == {"Draft": "Taslak"}


def test_accepting_writes_the_file_the_setting_points_at(qtbot, tmp_path, monkeypatch):
    """The setting is the contract with the run: a glossary saved elsewhere is not used."""
    target = tmp_path / "glossary.json"
    monkeypatch.setattr(tunables, "get", lambda key: str(target) if key == "translation.glossary_path" else None)
    saved: list[int] = []
    monkeypatch.setattr(tunables, "set_value", lambda key, value: saved.append(1))
    monkeypatch.setattr(tunables, "save", lambda: None)

    dialog = _dialog(qtbot)
    dialog.set_terms({"Report": "Rapor"})
    dialog._path = target

    dialog._accept()

    assert json.loads(target.read_text(encoding="utf-8")) == {"Report": "Rapor"}
    assert dialog.result() == GlossaryDialog.DialogCode.Accepted


def test_a_file_that_is_not_an_object_is_refused(qtbot, tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(
        "layoutkeep.ui.glossary_dialog.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(bad), ""),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        "layoutkeep.ui.glossary_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append("warned"),
    )

    dialog = _dialog(qtbot)
    dialog._load()

    assert warnings == ["warned"]
    assert dialog.terms() == {}


def test_the_caption_and_headers_are_translated(qtbot):
    UIStrings.set_language("tr")
    dialog = _dialog(qtbot)

    assert dialog.windowTitle() == UIStrings.GLOSSARY_TITLE
    assert dialog._table.horizontalHeaderItem(0).text() == UIStrings.GLOSSARY_SOURCE
    UIStrings.set_language("en")
