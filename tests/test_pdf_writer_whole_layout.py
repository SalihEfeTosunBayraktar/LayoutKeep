"""A block is not reported as fitting, or drawn, with the end of its text cut off.

Held-out PLOS ONE article: eight one-line blocks lost their last words, and neither fitting nor the
writer noticed. `insert_htmlbox` has a boundary case: when the box is exactly as tall as the lines
it holds - a 10 pt glyph box plus the writer's 3 pt slack is 13 pt, one line of 10 pt text at the
1.3 line height - it reports the text as fitting (spare 0, scale 1.0) and lays out only the first
line. Measured on the same Turkish line at 10 pt in Noto Serif: box heights 11, 12, 13.5, 14 and
20 pt are reported as not fitting; 13 pt is reported as fitting and draws half the sentence.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.fitting.fontmatch import resolve_font
from layoutkeep.writers.pdf_writer import measure_fit, write_pdf

_TURKISH = "Konum için koloni düzeyindeki model aşağıdaki denklemle verilmiştir"
_ENGLISH = "The colony level model for location is given by the equation below"


def _style(**overrides) -> Style:
    return Style(font_family="URWPalladioL-Roma", size=10.0, serif=True, **overrides)


def test_a_layout_cut_short_at_the_boundary_height_is_not_a_fit() -> None:
    drawn_face = resolve_font("URWPalladioL-Roma", "tr", serif_hint=True).resolved_path
    fits, _scale = measure_fit(_TURKISH, _style(font_path=drawn_face), BBox(72, 200, 352, 210))
    assert not fits


def test_the_writer_draws_the_whole_text_at_the_boundary_height(tmp_path: Path) -> None:
    src = tmp_path / "s.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 208), _ENGLISH, fontsize=9)
    doc.save(str(src))

    box = BBox(72, 200, 352, 210)  # a 10 pt glyph box, as embedded fonts report it
    below = BBox(150, 216, 260, 226)  # the next block 6 pt below: 3 pt of slack, no room to wrap
    blocks = [
        Block(id="line", role=BlockRole.BODY, bbox=box, source_text=_ENGLISH,
              lines=[Line(spans=[Span(text=_TURKISH, bbox=box, style=_style())], bbox=box)]),
        Block(id="eq", role=BlockRole.FORMULA, bbox=below,
              lines=[Line(spans=[Span(text="x = y + z", bbox=below, style=_style())], bbox=below)]),
    ]
    translated = Document(target_lang="tr", pages=[Page(number=1, width=612, height=792, blocks=blocks, source_ref="0")])
    out = tmp_path / "o.pdf"

    write_pdf(translated, src, out)

    drawn = " ".join(pymupdf.open(str(out))[0].get_text().split())
    assert "verilmiştir" in drawn, drawn


def test_a_control_character_from_extraction_does_not_end_the_drawn_text(tmp_path: Path) -> None:
    """Held-out PLOS ONE, page 13: a paragraph with inline math came out of the PDF with NUL
    characters where its symbol font had no mapping ("e\x00 x" for e to the minus x). The layout
    stops at a NUL - everything after it was missing from the page - and still reports a fit."""
    src = tmp_path / "s.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 208), _ENGLISH, fontsize=9)
    doc.save(str(src))
    box = BBox(72, 200, 540, 260)
    text = "Aktivasyon fonksiyonu tanh cosh e" + chr(0) + " x ve softmax ile düzeltilmiş doğrusal birim"
    block = Block(id="p", role=BlockRole.BODY, bbox=box, source_text=_ENGLISH,
                  lines=[Line(spans=[Span(text=text, bbox=box, style=_style())], bbox=box)])
    translated = Document(target_lang="tr", pages=[Page(number=1, width=612, height=792, blocks=[block], source_ref="0")])
    out = tmp_path / "o.pdf"

    write_pdf(translated, src, out)

    drawn = " ".join(pymupdf.open(str(out))[0].get_text().split())
    assert "softmax" in drawn and "doğrusal birim" in drawn, drawn
