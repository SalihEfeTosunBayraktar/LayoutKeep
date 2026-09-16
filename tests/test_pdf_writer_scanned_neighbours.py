"""Painting out a translated block must not paint out a neighbour that stays as scanned.

Book page 54, translated with the layout model: exercise 1-10's formula `a. x'z' + ...` was read
as a list item (translated, so painted out) and the line under it, `b. AC' + B'D + ...`, as a
formula (left as scanned). OCR boxes of adjacent lines overlap by about a point, and the cover
adds 1.5pt of padding on top, so the paint reached into the formula and wiped the top half of its
glyphs. Anything the writer is not going to redraw must keep every pixel it has.
"""

from __future__ import annotations

import numpy as np
import pymupdf
from PIL import Image

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style
from layoutkeep.writers.pdf_writer import _cover_scanned_blocks


def _block(bbox: BBox, text: str, role: BlockRole = BlockRole.LIST) -> Block:
    span = Span(text=text, bbox=bbox, style=Style(size=7.0))
    return Block(id=text, role=role, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)])


def _dark(page: pymupdf.Page, rect: pymupdf.Rect) -> int:
    pix = page.get_pixmap(dpi=288, clip=rect)
    grey = np.array(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L"))
    return int((grey < 128).sum())


def test_the_cover_stops_at_a_kept_neighbours_line() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=318, height=424)
    # Ink standing in for the scan: the translated line and, a point lower, the kept formula.
    page.draw_rect(pymupdf.Rect(104, 46, 174, 53), color=None, fill=(0, 0, 0))
    formula = pymupdf.Rect(103, 52.3, 193, 60.0)
    page.draw_rect(formula, color=None, fill=(0, 0, 0))

    translated = _block(BBox(104, 45.8, 174, 53.3), "a. x'z' + y'z'")
    kept = _block(BBox(103, 52.3, 193, 62.4), "b. AC' + B'D", role=BlockRole.FORMULA)
    before = _dark(page, formula)

    _cover_scanned_blocks(page, [translated], keep=[kept])

    assert _dark(page, formula) == before, "the formula lost pixels to its neighbour's cover"
    assert _dark(page, pymupdf.Rect(105, 47, 173, 51)) == 0, "the translated line was not covered"


def test_a_kept_line_inside_the_block_does_not_halve_its_cover() -> None:
    """Only a neighbour is given way to. A kept line whose middle lies inside the translated
    block's own box cannot be avoided by shrinking the cover, and shrinking would leave half of
    the source paragraph showing under its translation."""
    doc = pymupdf.open()
    page = doc.new_page(width=318, height=424)
    page.draw_rect(pymupdf.Rect(74, 100, 300, 160), color=None, fill=(0, 0, 0))
    paragraph = _block(BBox(74, 100, 300, 160), "a paragraph of prose", role=BlockRole.BODY)
    inline = _block(BBox(120, 126, 250, 134), "F = x + y", role=BlockRole.FORMULA)

    _cover_scanned_blocks(page, [paragraph], keep=[inline])

    assert _dark(page, pymupdf.Rect(76, 140, 298, 158)) == 0, "the lower half was left uncovered"
