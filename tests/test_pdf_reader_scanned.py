"""A scanned PDF - pages that are one big image with no text layer - must still be readable.

`computer-systems-Architecture.pdf` (524 pages, 0 extractable characters, one 600-DPI image per
page) read as 0 blocks / 0 translatable segments: the reader saw no text objects and returned an
empty document, so the app reported "no text to translate" on a book full of text.

`image_reader.is_scanned_page` already existed for exactly this decision but nothing in the
production path ever called it - it was reachable only from its own unit test. These tests pin
the wiring: a page with no text layer is rendered and handed to OCR, and the geometry that comes
back is in PDF points (not render pixels), because every writer and the fitting pass measure in
points.
"""

from __future__ import annotations

from itertools import pairwise

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from layoutkeep.readers.pdf_reader import read_pdf

#: Set in one place so the assertions and the fixture cannot drift apart.
SCANNED_TEXT = "The enable input may be activated with a zero."
#: The synthetic scan's page size, in points - near the real book's 318x424.
PAGE_W_PT, PAGE_H_PT = 320.0, 430.0
#: Render resolution of the fixture image. Deliberately not 72, so a reader that forgets to
#: convert pixels to points produces numbers far outside the page and the test catches it.
FIXTURE_DPI = 200.0


#: Line pitch of the multi-line fixture, in points. Chosen to look like real book setting
#: (~1.2x the type size) so the reader's size derivation is exercised the way a scan exercises it.
PARAGRAPH_PITCH_PT = 14.0
PARAGRAPH_LINES = (
    "The enable input may be activated",
    "with a zero or with a one signal",
    "level and some decoders have two",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_scanned_pdf(path, text: str = SCANNED_TEXT) -> None:
    """A PDF whose only content is a full-page raster of `text` - no text layer at all."""
    scale = FIXTURE_DPI / 72.0
    width_px, height_px = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    image = Image.new("RGB", (width_px, height_px), "white")
    ImageDraw.Draw(image).text((60, 120), text, fill="black", font=_font(30))

    png = path.parent / f"{path.stem}_page.png"
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))
    doc.close()


def build_scanned_paragraph_pdf(path) -> None:
    """A scan of a real paragraph: several lines set at a known, constant pitch."""
    scale = FIXTURE_DPI / 72.0
    width_px, height_px = int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    font = _font(int(PARAGRAPH_PITCH_PT * scale / 1.2))
    for i, line in enumerate(PARAGRAPH_LINES):
        draw.text((40, 100 + i * PARAGRAPH_PITCH_PT * scale), line, fill="black", font=font)

    png = path.parent / f"{path.stem}_page.png"
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))
    doc.close()


@pytest.fixture(scope="module")
def paragraph_doc(tmp_path_factory):
    path = tmp_path_factory.mktemp("scanned_para") / "para.pdf"
    build_scanned_paragraph_pdf(path)
    return read_pdf(path)


def test_font_size_reproduces_the_scans_line_pitch(paragraph_doc) -> None:
    """The size a scanned line is redrawn at has to reproduce the spacing it was scanned at.

    OCR reports a box per line, and that box's height is the *line pitch*, not the type size -
    measured over 19 multi-line blocks of `computer-systems-Architecture.pdf`, consecutive boxes
    sit 0.957 box-heights apart, i.e. they overlap. Taking the box height as the font size made
    every redrawn line ~1.2x taller than the line it replaced, so a 5-line paragraph needed 56pt
    of the 41pt box it had to fit in: 120 of 210 blocks were reported overflowing. The writer
    stacks lines at `_LINE_HEIGHT_RATIO` (1.2) x size, so size x 1.2 must come back to the pitch.
    """
    blocks = [b for page in paragraph_doc.pages for b in page.blocks if len(b.lines) >= 3]
    assert blocks, "fixture did not produce a multi-line block"
    block = blocks[0]

    tops = [line.bbox.y0 for line in block.lines if line.bbox is not None]
    pitch = sum(b - a for a, b in pairwise(tops)) / (len(tops) - 1)
    assert pitch == pytest.approx(PARAGRAPH_PITCH_PT, rel=0.15), "fixture pitch not recovered"

    size = block.dominant_style().size
    assert size * 1.2 == pytest.approx(pitch, rel=0.15), (
        f"size {size:.2f}pt renders at {size * 1.2:.2f}pt per line but the scan's pitch is "
        f"{pitch:.2f}pt - the paragraph will not fit the box it came from"
    )


def test_scanned_paragraph_fits_its_own_box(paragraph_doc) -> None:
    """The end-to-end property the user actually asked for: redrawing a block's own, untranslated
    text must not overflow the block. If it fails here it fails for every translation too."""
    blocks = [b for page in paragraph_doc.pages for b in page.blocks if len(b.lines) >= 3]
    block = blocks[0]
    needed = len(block.lines) * block.dominant_style().size * 1.2
    assert needed <= block.bbox.height * 1.1, (
        f"{len(block.lines)} lines need {needed:.1f}pt but the block box is "
        f"{block.bbox.height:.1f}pt"
    )


@pytest.fixture(scope="module")
def scanned_doc(tmp_path_factory):
    # OCR is slow enough that re-running it per test would dominate the suite; the Document is
    # read once and the assertions below only inspect it.
    path = tmp_path_factory.mktemp("scanned") / "scan.pdf"
    build_scanned_pdf(path)
    return read_pdf(path)


def test_scanned_pdf_yields_text(scanned_doc) -> None:
    """The regression that started this: 0 blocks on a page that plainly has text."""
    blocks = [b for page in scanned_doc.pages for b in page.blocks]
    assert blocks, "a scanned page produced no blocks - OCR fallback did not run"
    recovered = " ".join(b.text for b in blocks).lower()
    # Word-for-word rather than an exact string: OCR is allowed to differ in spacing/case, but
    # every word of real content has to survive or the translation is missing text.
    for word in SCANNED_TEXT.rstrip(".").lower().split():
        assert word in recovered, f"OCR lost {word!r}; got {recovered!r}"


def test_scanned_page_keeps_pdf_page_size(scanned_doc) -> None:
    """The Page must describe the PDF page in points, not the render in pixels."""
    page = scanned_doc.pages[0]
    assert page.width == pytest.approx(PAGE_W_PT, abs=1.0)
    assert page.height == pytest.approx(PAGE_H_PT, abs=1.0)


def test_scanned_block_geometry_is_in_points(scanned_doc) -> None:
    """Bounding boxes come out of OCR in render pixels; left unconverted they would be ~2.8x
    the page and every writer would place the text off-page."""
    page = scanned_doc.pages[0]
    for block in page.blocks:
        assert 0 <= block.bbox.x0 < block.bbox.x1 <= page.width + 1, block.bbox
        assert 0 <= block.bbox.y0 < block.bbox.y1 <= page.height + 1, block.bbox


def test_scanned_block_font_size_is_plausible(scanned_doc) -> None:
    """A 30px glyph box at 200 DPI is ~11pt. If the DPI were assumed to be the PIL default of
    96 the size would come out ~2x too large and the refitted text would overflow its box."""
    sizes = [
        span.style.size
        for page in scanned_doc.pages
        for block in page.blocks
        for line in block.lines
        for span in line.spans
    ]
    assert sizes
    assert all(4.0 <= size <= 30.0 for size in sizes), sizes
