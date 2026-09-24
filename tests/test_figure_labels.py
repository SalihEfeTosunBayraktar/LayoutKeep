"""Labels inside a figure: kept as they are by default, translated as words when asked.

Think Python p. 97: a stack diagram's labels translated renamed its variables ("letters" ->
"harfler") and lost "__main__", so text inside a picture region is part of the picture. With
translation.figure_text on, a label that reads as words is translated in its own box; names,
signals and code stay part of the picture either way.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from test_pdf_reader_digital_layout import _Detector

from layoutkeep.core import tunables
from layoutkeep.core.docir import BlockRole
from layoutkeep.fitting.growth import may_grow, may_grow_right
from layoutkeep.readers._nonprose import is_prose_label
from layoutkeep.readers.pdf_reader import read_pdf


def test_words_are_a_label_names_and_signals_are_not():
    assert is_prose_label("Instruction stream byte queue")
    assert is_prose_label("Arithmetic logic unit")
    for text in ("AX", "ALE RD WR", "D0-D7", "__main__", "delete_head", "letters", "C-BUS"):
        assert not is_prose_label(text), text


def _figure(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((100, 150), "Instruction stream byte queue", fontsize=8)
    page.insert_text((100, 170), "AX BX CX", fontsize=8)
    doc.save(str(path))


def _roles(src: Path) -> dict[str, BlockRole]:
    page = read_pdf(src, layout=_Detector([("picture", (80, 130, 400, 190))])).pages[0]
    return {" ".join(b.text.split()): b.role for b in page.blocks}


def test_by_default_a_figures_text_stays_part_of_it(tmp_path: Path) -> None:
    src = tmp_path / "fig.pdf"
    _figure(src)
    assert set(_roles(src).values()) == {BlockRole.FIGURE}


def test_with_the_setting_on_a_prose_label_is_translated_in_its_own_box(tmp_path: Path) -> None:
    src = tmp_path / "fig.pdf"
    _figure(src)
    tunables.set_value("translation.figure_text", True)
    try:
        roles = _roles(src)
    finally:
        tunables.set_value("translation.figure_text", False)
    assert roles["Instruction stream byte queue"] is BlockRole.FIGURE_LABEL
    assert roles["AX BX CX"] is BlockRole.FIGURE
    label = next(b for b in read_pdf(src).pages[0].blocks)  # any block: role checked below
    label.role = BlockRole.FIGURE_LABEL
    assert not may_grow(label) and not may_grow_right(label)
