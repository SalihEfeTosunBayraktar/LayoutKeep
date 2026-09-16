"""On a scanned page, a block with no words is left exactly as it was scanned.

A Karnaugh map, a truth table, a set of axis tick labels: OCR reads the digits correctly but has
no idea they form a grid, so it hands back a block per horizontal run. The writer then clears
that area and re-typesets the run as a line of prose, and the figure is destroyed - page 28 of
`computer-systems-Architecture.pdf` came out with `{123`, `{14576` and `1112131514 A 108` where
the maps used to be.

Confidence does not identify these: measured on that page, `1112131514 A 108` has an OCR
confidence of 1.00. The recognition is right; it is the two-dimensional structure that is lost,
and nothing downstream can recover it from a flat string.

What does identify them is that they carry no words. Measured over that page's 34 blocks:

    grid fragments   0.00 - 0.18 letters per character
    real text        0.50 - 1.00   ('(a) Two-variable map', 'adjacent squares')

and there is nothing in between. A block like that has nothing to translate - protection
already answers it with its own source - so redrawing it cannot improve it and demonstrably
makes it worse. The scan is left alone.
"""

from __future__ import annotations

import numpy as np
import pymupdf
import pytest
from PIL import Image, ImageDraw

from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf
from tests.test_pdf_reader_scanned import FIXTURE_DPI, PAGE_H_PT, PAGE_W_PT, _font

#: A line of prose, and a row of digits standing in for a map/table row.
PROSE = "The minterm represented by a square"
DIGITS = "0 1 3 2 4 5 7 6"
#: Where the digit row sits, in points.
DIGITS_Y_PT = 200.0
_DARK = 160


def _build(path) -> None:
    scale = FIXTURE_DPI / 72.0
    image = Image.new("RGB", (int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)), "white")
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    draw.text((40, 100), PROSE, fill="black", font=font)
    draw.text((40, DIGITS_Y_PT * scale), DIGITS, fill="black", font=font)

    png = path.parent / f"{path.stem}.png"
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))
    doc.close()


def _ink(page: pymupdf.Page, clip: pymupdf.Rect) -> int:
    pix = page.get_pixmap(dpi=150, clip=clip)
    grey = np.array(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L"))
    return int((grey < _DARK).sum())


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wordless")
    src = tmp / "scan.pdf"
    _build(src)
    doc = read_pdf(src)
    assert doc.pages[0].blocks, "fixture produced no OCR blocks"
    # Stand in for a translation, the way `apply_segments` does it: the pre-translation text is
    # kept on `source_text`, which is what decides whether a block had words to begin with.
    for _page, block in doc.iter_blocks():
        block.source_text = block.text
        for line_index, line in enumerate(block.lines):
            for span_index, span in enumerate(line.spans):
                span.text = "x" if (line_index == 0 and span_index == 0) else ""
    out = tmp / "out.pdf"
    write_pdf(doc, src, out)
    return src, out


def _band(y_pt: float, height: float = 22.0) -> pymupdf.Rect:
    return pymupdf.Rect(0, y_pt - 6, PAGE_W_PT, y_pt + height)


def test_the_digit_row_is_untouched(rendered) -> None:
    """Pixel for pixel: the scan of a wordless block must survive into the output."""
    src_path, out_path = rendered
    band = _band(DIGITS_Y_PT)
    with pymupdf.open(src_path) as src, pymupdf.open(out_path) as out:
        assert _ink(out[0], band) == _ink(src[0], band), (
            "the digit row was cleared and re-typeset; on a real page that destroys the figure"
        )


def test_prose_is_still_replaced(rendered) -> None:
    """The skip must not turn into 'leave the scan alone', or nothing gets translated."""
    src_path, out_path = rendered
    band = _band(100 / (FIXTURE_DPI / 72.0))
    with pymupdf.open(src_path) as src, pymupdf.open(out_path) as out:
        assert _ink(out[0], band) < _ink(src[0], band) * 0.6, "the prose line was not replaced"
