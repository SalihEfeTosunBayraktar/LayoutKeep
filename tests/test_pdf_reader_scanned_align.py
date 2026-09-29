"""A centred heading on a scanned page must come back centred.

`pdf_reader` infers a block's alignment from where it sits on the page, so a chapter title or a
figure caption is re-drawn where it was. `image_reader` never set `Block.align` at all - it has
no `align=` assignment anywhere - so every block OCR produced defaulted to "left" and every
centred line on a 524-page scan was redrawn hard against the left margin.

Reported from the output, not deduced: "metinler bir kenara kayip yaslanmis" - the text has
slid over and is pressed against one side.
"""

from __future__ import annotations

import pymupdf
import pytest
from PIL import Image, ImageDraw

from layoutkeep.readers.pdf_reader import read_pdf
from tests.test_pdf_reader_scanned import FIXTURE_DPI, PAGE_H_PT, PAGE_W_PT, _font

CENTRED = "Figure 1-7 Maps"
LEFT = "The minterm represented by a square is determined"


def _build(path) -> None:
    scale = FIXTURE_DPI / 72.0
    width_px, height_px = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    # Centred: measured, then placed symmetrically about the page midline.
    w = draw.textlength(CENTRED, font=font)
    draw.text(((width_px - w) / 2, 120), CENTRED, fill="black", font=font)
    # Left: hugging the left margin, well away from centre.
    draw.text((30, 300), LEFT, fill="black", font=font)

    png = path.parent / f"{path.stem}.png"
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))
    doc.close()


@pytest.fixture(scope="module")
def scanned(tmp_path_factory):
    path = tmp_path_factory.mktemp("align") / "align.pdf"
    _build(path)
    return read_pdf(path)


def _find(doc, needle: str):
    for _page, block in doc.iter_blocks():
        if needle.split()[0].lower() in block.text.lower():
            return block
    raise AssertionError(f"OCR did not find {needle!r}")


def test_a_centred_line_is_marked_centred(scanned) -> None:
    block = _find(scanned, CENTRED)
    assert block.align == "center", (
        f"centred caption came back align={block.align!r}; it will be redrawn against the "
        f"left margin"
    )


def test_a_left_aligned_line_stays_left(scanned) -> None:
    """The guard against over-eager centring: ordinary body text must not move."""
    block = _find(scanned, LEFT)
    assert block.align in ("left", "justify"), block.align
