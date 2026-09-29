"""Glossary export and the term-candidate preview.

Sözlüğü dışa aktarma ve terim adaylarının önizlemesi.

Export writes a copy in the format its suffix names and must read back as the same list through the
run's own reader (`Glossary.load`); it never moves the file the setting points at. The preview shows
every candidate ticked, and only what is still ticked when the person confirms enters the table.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.core import tunables
from layoutkeep.core.terms import Candidate
from layoutkeep.providers.glossary import Glossary, save_terms


@pytest.fixture(autouse=True)
def _restore_tunables():
    """The editor and these tests write tunables; the suite must not inherit them."""
    before = {spec.key: tunables.get(spec.key) for spec in tunables.TUNABLES}
    yield
    for key, value in before.items():
        tunables.set_value(key, value)


TERMS = {"tax return": "vergi beyannamesi", "a, b": "virgüllü; terim", "Türkiye": "Türkiye"}


@pytest.mark.parametrize("suffix", [".csv", ".tsv", ".txt", ".json"])
def test_an_exported_glossary_reads_back_as_the_same_list(tmp_path: Path, suffix: str) -> None:
    path = save_terms(tmp_path / f"glossary{suffix}", TERMS)

    assert Glossary.load(path).terms == TERMS


def test_a_table_export_starts_with_a_header_row(tmp_path: Path) -> None:
    path = save_terms(tmp_path / "glossary.csv", TERMS)

    assert path.read_text(encoding="utf-8").splitlines()[0] == "source,target"


def _dialog(qtbot):
    from layoutkeep.ui.glossary_dialog import GlossaryDialog

    dialog = GlossaryDialog()
    qtbot.addWidget(dialog)
    dialog.set_terms(TERMS)
    return dialog


def test_the_editor_exports_a_copy_and_keeps_the_runs_file(qtbot, tmp_path: Path) -> None:
    configured = tmp_path / "run.json"
    save_terms(configured, {"old": "eski"})
    tunables.set_value("translation.glossary_path", str(configured))
    dialog = _dialog(qtbot)
    dialog.set_terms(TERMS)

    out = dialog.export_to(tmp_path / "export.tsv")

    assert out is not None and Glossary.load(out).terms == TERMS
    assert tunables.get("translation.glossary_path") == str(configured)
    assert Glossary.load(configured).terms == {"old": "eski"}, "export must not write the run's file"
    assert "3" in dialog._status.text()


def test_the_editor_loads_a_csv_file(qtbot, tmp_path: Path, monkeypatch) -> None:
    """The file filter offered CSV and TSV, but the editor read only JSON and refused the rest."""
    from PySide6.QtWidgets import QFileDialog

    table = save_terms(tmp_path / "terms.csv", TERMS)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(table), ""))
    dialog = _dialog(qtbot)
    dialog.set_terms({})

    dialog._load()

    assert dialog.terms() == TERMS


def _candidates() -> list[Candidate]:
    return [Candidate("estimated tax", 9), Candidate("your return", 7), Candidate("penalty", 4)]


def test_the_preview_offers_every_candidate_ticked_with_its_count(qtbot) -> None:
    from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

    preview = TermCandidatesDialog(_candidates())
    qtbot.addWidget(preview)

    assert preview.chosen() == ["estimated tax", "your return", "penalty"]
    assert preview._table.item(0, 1).text() == "9"


def test_only_the_ticked_candidates_are_chosen(qtbot) -> None:
    from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

    preview = TermCandidatesDialog(_candidates())
    qtbot.addWidget(preview)
    preview.set_ticked("your return", False)
    assert preview.chosen() == ["estimated tax", "penalty"]

    preview._tick_all(False)
    assert preview.chosen() == []


def _document_with_terms(tmp_path: Path) -> Path:
    import pymupdf

    source = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for index in range(6):
        page.insert_text((60, 80 + index * 40), "estimated tax penalty and estimated tax payment",
                         fontsize=11)
    doc.save(str(source))
    doc.close()
    return source


def test_a_cancelled_preview_adds_nothing(qtbot, tmp_path: Path, monkeypatch) -> None:
    from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

    monkeypatch.setattr(TermCandidatesDialog, "exec", lambda self: 0)
    dialog = _dialog(qtbot)
    dialog.set_terms({})
    dialog.set_document(_document_with_terms(tmp_path))

    dialog._suggest()

    assert dialog.terms() == {}


def test_an_unticked_candidate_stays_out_of_the_glossary(qtbot, tmp_path: Path, monkeypatch) -> None:
    from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

    def untick_first(self) -> int:
        self.set_ticked(self.chosen()[0], False)
        return 1

    offered: list[list[str]] = []
    real_init = TermCandidatesDialog.__init__

    def spy_init(self, candidates, parent=None) -> None:
        offered.append([candidate.phrase for candidate in candidates])
        real_init(self, candidates, parent)

    monkeypatch.setattr(TermCandidatesDialog, "__init__", spy_init)
    monkeypatch.setattr(TermCandidatesDialog, "exec", untick_first)
    dialog = _dialog(qtbot)
    dialog.set_terms({})
    dialog.set_document(_document_with_terms(tmp_path))

    dialog._suggest()

    assert offered and offered[0][0] not in dialog.terms()
    assert set(dialog.terms()) == set(offered[0][1:])


def test_the_suggestion_count_comes_from_the_setting(qtbot, tmp_path: Path, monkeypatch) -> None:
    from layoutkeep.ui.term_candidates_dialog import TermCandidatesDialog

    monkeypatch.setattr(TermCandidatesDialog, "exec", lambda self: 1)
    tunables.set_value("translation.suggest_limit", 5)
    dialog = _dialog(qtbot)
    dialog.set_terms({})
    dialog.set_document(_document_with_terms(tmp_path))

    dialog._suggest()

    assert 0 < len(dialog.terms()) <= 5
