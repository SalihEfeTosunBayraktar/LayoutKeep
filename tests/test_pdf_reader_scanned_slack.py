"""A scanned block may use the blank paper under it, and nothing else.

Turkish runs longer than English, so a paragraph that filled its box in the source needs another
line in translation. `fitting/` has two answers and no third: shrink the type to a readability
floor, or ask for a shorter rendering. When neither is enough the block is flagged as
overflowing - 17 of 193 blocks on six pages of `computer-systems-Architecture.pdf`.

On a scanned page there is usually somewhere to put that line. Measured over 38 prose blocks of
those six pages: the median vertical gap below a block is 13.2pt and 26 of the 38 have room for
at least one more line, because the space between paragraphs is blank paper.

Taking it is only safe if it really is blank. The bound cannot be "the next block": a figure
that OCR found no text in is not a block, so a paragraph above it would grow across the figure,
and `pdf_writer._cover_scanned_blocks` would then paint the figure out to clear the source text
underneath - which is exactly the diagram-destroying bug that `_LINE_JOIN_GAP_RATIO` was added
to stop. So the reader looks at the actual pixels and stops at the first row with ink in it.
"""

from __future__ import annotations

import pymupdf
import pytest
from PIL import Image, ImageDraw

from layoutkeep.readers.pdf_reader import read_pdf
from tests.test_pdf_reader_scanned import (
    FIXTURE_DPI,
    PAGE_H_PT,
    PAGE_W_PT,
    PARAGRAPH_LINES,
    PARAGRAPH_PITCH_PT,
    _font,
)


def _build(path, *, rule_at_pt: float | None) -> None:
    """A scanned paragraph with a lot of blank paper under it, optionally interrupted by a rule
    standing in for the top edge of a figure."""
    scale = FIXTURE_DPI / 72.0
    image = Image.new("RGB", (int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)), "white")
    draw = ImageDraw.Draw(image)
    font = _font(int(PARAGRAPH_PITCH_PT * scale / 1.2))
    for i, line in enumerate(PARAGRAPH_LINES):
        draw.text((40, 100 + i * PARAGRAPH_PITCH_PT * scale), line, fill="black", font=font)
    if rule_at_pt is not None:
        y = rule_at_pt * scale
        draw.rectangle([40, y, PAGE_W_PT * scale - 40, y + 3], fill="black")

    png = path.parent / f"{path.stem}.png"
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    doc.save(str(path))
    doc.close()


def _paragraph(doc):
    blocks = [b for page in doc.pages for b in page.blocks if len(b.lines) >= 3]
    assert blocks, "fixture produced no multi-line block"
    return blocks[0]


@pytest.fixture(scope="module")
def open_page(tmp_path_factory):
    path = tmp_path_factory.mktemp("slack_open") / "open.pdf"
    _build(path, rule_at_pt=None)
    return read_pdf(path)


@pytest.fixture(scope="module")
def blocked_page(tmp_path_factory):
    """The same paragraph with a rule a few points below it - a figure edge OCR cannot see."""
    path = tmp_path_factory.mktemp("slack_blocked") / "blocked.pdf"
    # Just under the paragraph: text starts at 100px/FIXTURE_DPI and runs three lines.
    text_bottom_pt = (100 / (FIXTURE_DPI / 72.0)) + 3 * PARAGRAPH_PITCH_PT
    _build(path, rule_at_pt=text_bottom_pt + 4.0)
    return read_pdf(path)


def test_a_block_over_blank_paper_gets_room_for_another_line(open_page) -> None:
    """Enough slack to absorb one line of a longer language, which is what the overflow was."""
    block = _paragraph(open_page)
    lines = len(block.lines)
    size = block.dominant_style().size
    # The reader grows the box to exactly this height, so compare with float slop rather than
    # a bare `>=` - the two differ in the last bit.
    needed_for_one_more = (lines + 1) * size * 1.2 - 1e-6
    assert block.bbox.height >= needed_for_one_more, (
        f"{lines} lines at {size:.2f}pt have {block.bbox.height:.1f}pt; one more line needs "
        f"{needed_for_one_more:.1f}pt and the page below the block is blank"
    )


def test_growth_stops_at_ink(blocked_page) -> None:
    """A figure's top edge is not a block, so only the pixels can stop the growth. If this
    regresses, the writer paints the figure out when it clears the source text."""
    block = _paragraph(blocked_page)
    rule_top_pt = (100 / (FIXTURE_DPI / 72.0)) + 3 * PARAGRAPH_PITCH_PT + 4.0
    assert block.bbox.y1 <= rule_top_pt, (
        f"block grew to {block.bbox.y1:.1f}pt, past ink at {rule_top_pt:.1f}pt"
    )


def test_growth_never_leaves_the_page(open_page) -> None:
    page = open_page.pages[0]
    for block in page.blocks:
        assert block.bbox.y1 <= page.height + 1, block.bbox
