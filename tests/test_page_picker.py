"""The visual page picker: thumbnails in, the range field's own text out.

Görsel sayfa seçici: küçük resimler girer, aralık alanının kendi metni çıkar.

The picker writes the same text the field takes, so the property that matters is the round trip:
whatever pages are ticked, `parse_page_range` reads the written text back as exactly those pages.
The rest pins the wiring - the button appears with the custom range and writes into the field.
"""

from __future__ import annotations

import random
from pathlib import Path

import pymupdf
import pytest

from layoutkeep.core.range_helper import format_page_range, parse_page_range


@pytest.mark.parametrize(
    ("pages", "text"),
    [({1}, "1"), ({1, 2, 3, 5}, "1-3, 5"), ({2, 4, 6}, "2, 4, 6"), ({7, 8, 9, 10}, "7-10"), (set(), "")],
)
def test_pages_are_written_as_the_shortest_range(pages: set[int], text: str) -> None:
    assert format_page_range(pages) == text


def test_any_selection_reads_back_as_itself() -> None:
    rng = random.Random(7)
    for _ in range(200):
        total = rng.randint(1, 60)
        pages = {page for page in range(1, total + 1) if rng.random() < 0.4} or {1}
        assert parse_page_range(format_page_range(pages), total) == pages


def _pdf(path: Path, pages: int) -> Path:
    doc = pymupdf.open()
    for index in range(pages):
        doc.new_page(width=300, height=420).insert_text((30, 60), f"page {index + 1}", fontsize=18)
    doc.save(str(path))
    doc.close()
    return path


def test_the_picker_starts_from_the_current_range_and_writes_it_back(qtbot, tmp_path: Path) -> None:
    from layoutkeep.ui.page_picker import PagePickerDialog

    dialog = PagePickerDialog(_pdf(tmp_path / "doc.pdf", 6), {2, 3})
    qtbot.addWidget(dialog)
    assert dialog.selected_pages() == {2, 3}
    assert dialog.range_text() == "2-3"

    dialog.set_page(6, True)
    assert dialog.range_text() == "2-3, 6"
    dialog.set_all(True)
    assert dialog.range_text() == "", "every page ticked is the whole document"


def test_nothing_ticked_cannot_be_confirmed(qtbot, tmp_path: Path) -> None:
    """An empty range means "the whole document" to the field, the opposite of what was ticked."""
    from layoutkeep.ui.page_picker import PagePickerDialog

    dialog = PagePickerDialog(_pdf(tmp_path / "doc.pdf", 3))
    qtbot.addWidget(dialog)
    dialog.set_all(False)

    assert not dialog._ok.isEnabled()


def test_every_page_gets_a_thumbnail(qtbot, tmp_path: Path) -> None:
    from layoutkeep.ui.page_picker import PagePickerDialog

    dialog = PagePickerDialog(_pdf(tmp_path / "doc.pdf", 13))
    qtbot.addWidget(dialog)
    dialog.render_all()

    assert all(not dialog._list.item(index).icon().isNull() for index in range(13))


def test_a_file_that_is_not_a_pdf_is_refused(qtbot, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QWidget

    from layoutkeep.ui.page_picker import pick_pages

    parent = QWidget()
    qtbot.addWidget(parent)
    epub = tmp_path / "book.epub"
    epub.write_bytes(b"not really")

    assert pick_pages(parent, str(epub), "") is None
    assert pick_pages(parent, "", "") is None


def test_the_setup_screen_offers_the_picker_with_the_custom_range(qtbot, tmp_path, monkeypatch) -> None:
    from layoutkeep.ui.job_setup import JobSetupWidget
    from layoutkeep.ui.page_picker import PagePickerDialog

    def keep_first_two(self) -> int:
        self.set_all(False)
        self.set_page(1, True)
        self.set_page(2, True)
        return 1

    monkeypatch.setattr(PagePickerDialog, "exec", keep_first_two)
    screen = JobSetupWidget()
    qtbot.addWidget(screen)
    assert screen._range_pick.isHidden(), "hidden while the whole document is chosen"

    screen._range_mode.setCurrentIndex(1)
    assert not screen._range_pick.isHidden()

    screen._input_path.setText(str(_pdf(tmp_path / "doc.pdf", 5)))
    screen._range_pick.click()

    assert screen._range_input.text() == "1-2"
