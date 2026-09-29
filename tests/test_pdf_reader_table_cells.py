"""A table cell that wraps over several lines is one block, not one block per line.

Arm E, tr_shk_2828: a table's cells came out one line each - "Mülki", "İdare", "Amirliği" - so each
word was translated without its neighbours ("aybaşında" -> "at the full moon") and every one
outgrew its one-line box (16 of the page's blocks below the readability floor). The lines of one
cell are stacked in one column with no rule between them; a rule, or a gap wider than the line
spacing, still starts a new cell.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from test_pdf_reader_digital_layout import _Detector

from layoutkeep.readers.pdf_reader import read_pdf


def _table(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    # Column 1, row 1: a cell wrapped over three lines. Column 2, row 1: one line.
    for i, word in enumerate(("Mulki", "Idare", "Amirligi")):
        page.insert_text((80, 110 + i * 9), word, fontsize=7)
    page.insert_text((200, 110), "yurürlüge", fontsize=7)
    # A rule, then row 2 in column 1.
    page.draw_line((75, 134), (300, 134), width=0.5)
    page.insert_text((80, 144), "Bakanlar", fontsize=7)
    page.insert_text((80, 153), "Kurulu", fontsize=7)
    doc.save(str(path))


def test_the_lines_of_one_cell_are_one_block_and_rows_and_columns_stay_apart(tmp_path: Path) -> None:
    src = tmp_path / "table.pdf"
    _table(src)
    page = read_pdf(src, layout=_Detector([("table", (70, 95, 320, 160))])).pages[0]
    texts = sorted(" ".join(b.text.split()) for b in page.blocks)
    assert texts == ["Bakanlar Kurulu", "Mulki Idare Amirligi", "yurürlüge"], texts
