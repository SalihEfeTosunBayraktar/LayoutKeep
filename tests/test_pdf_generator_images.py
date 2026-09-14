"""An embedded image must reach a generated PDF, not just its text.

Found evaluating docx->pdf as a phase-2 candidate (tools/audit/faz2_candidates.py): the pair
carried 100% of the words but 0 of 1 images. Root cause: a DOCX-sourced page has no real
geometry (width=0), so generate_pdf_from_docir routes it through `_draw_flowing_page`, which
iterated `blocks_in_reading_order()` - text blocks only, never `page_data.images`. The same gap
existed in `_draw_positioned_page` for any source with real per-image bboxes.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    ImageRef,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.writers.pdf_generator import generate_pdf_from_docir

# A minimal valid 1x1 red PNG.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_an_image_on_a_geometry_less_page_reaches_the_pdf(tmp_path: Path) -> None:
    """The DOCX->PDF path: page.width == 0, so this goes through _draw_flowing_page."""
    image = ImageRef(bbox=BBox(0, 0, 0, 0), data=base64.b64encode(_PNG_1X1).decode(), fmt="png")
    page = Page(number=1, width=0, height=0, blocks=[], images=[image], source_ref="0")
    doc = Document(pages=[page])

    out = tmp_path / "out.pdf"
    generate_pdf_from_docir(doc, out)

    with pymupdf.open(out) as pdf:
        total_images = sum(len(p.get_images()) for p in pdf)
    assert total_images == 1


def test_an_image_on_a_positioned_page_reaches_the_pdf(tmp_path: Path) -> None:
    """The has_layout path: a page with real width/height, a positioned block (so
    generate_pdf_from_docir picks _draw_positioned_page) and a positioned picture."""
    line = Line(
        spans=[Span(text="caption", bbox=BBox(10, 130, 110, 145), style=Style())],
        bbox=BBox(10, 130, 110, 145),
    )
    block = Block(id="b1", role=BlockRole.BODY, bbox=BBox(10, 130, 110, 145), lines=[line])
    image = ImageRef(bbox=BBox(10, 10, 110, 110), data=base64.b64encode(_PNG_1X1).decode(), fmt="png")
    page = Page(number=1, width=595, height=842, blocks=[block], images=[image], source_ref="0")
    doc = Document(pages=[page])

    out = tmp_path / "out.pdf"
    generate_pdf_from_docir(doc, out)

    with pymupdf.open(out) as pdf:
        total_images = sum(len(p.get_images()) for p in pdf)
    assert total_images == 1
