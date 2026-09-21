"""Clearing a scanned block must not leave a rectangle on paper that is not a flat colour.

NASA report cover, translated: every translated block sat on a visible patch. The reader's
background colour was right on average (201,164,136 against paper 204,165,137), but a yellowed
scan is not one colour - on that page the paper runs from 174 to 206 - and the writer painted a
single flat rectangle, whose edge shows wherever the paper around it differs. Only the ink should
be removed, and the paper under it continued from its surroundings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw

import layoutkeep.writers.pdf_writer as pdf_writer
from layoutkeep.core.docir import apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf
from tests.test_pdf_reader_scanned import FIXTURE_DPI, PAGE_H_PT, PAGE_W_PT, _font

_TEXT_TOP_PT = 120.0


def _tinted_scan(path: Path) -> None:
    scale = FIXTURE_DPI / 72.0
    width, height = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    # Yellowed paper that darkens from left to right, as a stained or unevenly lit scan does.
    ramp = np.linspace(0.0, 1.0, width)[None, :, None]
    light, dark = np.array([236, 206, 176]), np.array([176, 146, 118])
    paper = (light + (dark - light) * ramp) * np.ones((height, 1, 1))
    image = Image.fromarray(paper.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    for row, text in enumerate(("The enable input may be activated", "with a zero or with a one signal")):
        draw.text((int(30 * scale), int((_TEXT_TOP_PT + row * 16) * scale)), text, fill=(40, 30, 25), font=font)
    png = path.with_suffix(".png")
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))


def _render(path: Path) -> np.ndarray:
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(dpi=100)
        return np.array(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(int)


def test_no_rectangle_edge_is_left_on_uneven_paper(tmp_path: Path) -> None:
    src = tmp_path / "tinted.pdf"
    _tinted_scan(src)
    doc = read_pdf(src)
    blocks = [b for _p, b in doc.iter_blocks()]
    assert blocks, "fixture produced no OCR blocks"
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = "x"  # nearly nothing drawn back, so the cleared area is mostly bare paper
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    before, after = _render(src), _render(out)
    scale = 100 / 72.0
    box = max(blocks, key=lambda b: b.bbox.width).bbox
    x1 = int((box.x1 + 4) * scale)
    y0, y1 = int((box.y0 - 4) * scale), int((box.y1 + 4) * scale)
    # Just outside the right edge of the cleared area, and just inside it: on untouched paper
    # these differ only by the ramp over a few pixels. A flat fill makes them differ by the whole
    # distance between the block's average colour and the paper at its edge.
    inside = after[y0 + 6 : y1 - 6, x1 - 9 : x1 - 5].reshape(-1, 3).mean(0)
    outside = after[y0 + 6 : y1 - 6, x1 + 2 : x1 + 6].reshape(-1, 3).mean(0)
    paper_step = np.abs(before[y0 + 6 : y1 - 6, x1 - 9 : x1 - 5].reshape(-1, 3).mean(0)
                        - before[y0 + 6 : y1 - 6, x1 + 2 : x1 + 6].reshape(-1, 3).mean(0)).max()
    assert np.abs(inside - outside).max() <= paper_step + 6, (inside.round(), outside.round(), paper_step)


def test_the_source_ink_is_still_removed(tmp_path: Path) -> None:
    src = tmp_path / "tinted.pdf"
    _tinted_scan(src)
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = "x"
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)
    after = _render(out)
    scale = 100 / 72.0
    band = after[int((_TEXT_TOP_PT + 2) * scale) : int((_TEXT_TOP_PT + 28) * scale), int(120 * scale) : int(260 * scale)]
    assert (band.mean(2) < 90).sum() == 0, "source glyphs survived the clearing"


def test_the_panel_rule_never_changes_a_paper_page(tmp_path: Path) -> None:
    """The user's worry: "don't break the page translations while fixing the cover". Measured.

    The same source and the same target text, written twice - the panel rule at 120 and effectively
    off at 255. On a paper page the two runs must be identical pixel for pixel: the rule exists for
    coloured covers, and if it ever leaks onto ordinary pages this test fails and says so.
    """
    src = tmp_path / "tinted.pdf"
    _tinted_scan(src)

    rendered = []
    for threshold in (120, 255):
        pdf_writer._SCAN_PAPER_MAX_SATURATION = threshold
        doc = read_pdf(src)
        segments = segments_from_document(doc)
        for seg in segments:
            seg.target = "the same words in both runs"
        apply_segments(doc, segments)
        out = tmp_path / f"out_{threshold}.pdf"
        pdf_writer.write_pdf(doc, src, out)
        rendered.append(_render(out))

    on, off = rendered
    differing = int((np.abs(on - off).max(2) > 0).sum())
    assert differing == 0, f"the panel rule changed {differing} pixels of an ordinary paper page"


def test_a_coloured_panel_is_painted_over_instead_of_ink_erased(tmp_path: Path) -> None:
    """The Elmasri cover: a yellow title on a red panel. Otsu splits the box into two populations and
    on a panel the DARKER one is the background - so erasing "ink" took the panel and left the title
    showing, while returning True, which meant the rectangle fill the caller keeps as a fallback never
    ran. Measured median saturation: 201 on that cover, 52-56 on yellowed paper. A saturated box now
    declines and the caller paints its rectangles.
    """
    scale = FIXTURE_DPI / 72.0
    width, height = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    image = Image.new("RGB", (width, height), (176, 32, 40))
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    top = int(_TEXT_TOP_PT * scale)
    draw.text((int(40 * scale), top), "Fundamentals of Database Systems", fill=(240, 236, 80), font=font)
    png = tmp_path / "cover.png"
    image.save(png)
    src = tmp_path / "cover.pdf"
    raw = pymupdf.open()
    page = raw.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    raw.save(str(src))

    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = "Veritabanı Sistemleri"
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    after = _render(out)
    band = after[
        int((_TEXT_TOP_PT - 2) * scale) : int((_TEXT_TOP_PT + 14) * scale),
        int(35 * scale) : int(280 * scale),
    ]
    yellow = ((band[:, :, 0] > 170) & (band[:, :, 1] > 170) & (band[:, :, 2] < 140)).sum()
    assert yellow == 0, f"the source title is still visible on the panel ({yellow} yellow pixels)"

    patch = after[
        int((_TEXT_TOP_PT - 6) * scale) : int((_TEXT_TOP_PT + 18) * scale),
        int(35 * scale) : int(280 * scale),
    ]
    assert patch[:, :, 2].mean() < 110, "the fill must be the panel's own colour, not a white patch"


def test_a_ruled_line_through_the_cleared_box_survives(tmp_path: Path) -> None:
    """Book page 101, round 5: clearing a table's header words also erased the table's rules.
    Everything darker than the box's paper was taken for ink, and a rule crossing the box is dark.
    Glyph strokes are at most about a letter wide; a rule runs far longer than the type is tall."""
    scale = FIXTURE_DPI / 72.0
    width, height = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    image = Image.new("RGB", (width, height), (236, 226, 210))
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    top = int(_TEXT_TOP_PT * scale)
    draw.text((int(40 * scale), top), "Message xyz Parity odd even", fill=(30, 30, 30), font=font)
    rule_y = top + int(13 * scale)
    draw.rectangle((int(30 * scale), rule_y, int(290 * scale), rule_y + max(2, int(0.8 * scale))), fill=(30, 30, 30))
    png = tmp_path / "ruled.png"
    image.save(png)
    src = tmp_path / "ruled.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(src))

    read = read_pdf(src)
    segments = segments_from_document(read)
    for seg in segments:
        seg.target = "x"
    apply_segments(read, segments)
    # Stand in for a cleared box that reaches down over the rule, as padding and growth make it.
    for _p, block in read.iter_blocks():
        block.bbox.y1 = max(block.bbox.y1, _TEXT_TOP_PT + 16)
    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)

    rendered = _render(out)
    s = 100 / 72.0
    rule_row = int((rule_y / scale + 0.4) * s)
    row = rendered[rule_row - 1 : rule_row + 2, int(60 * s) : int(260 * s)].mean(2)
    assert (row.min(axis=0) < 120).mean() > 0.9, "the rule was erased with the words"
