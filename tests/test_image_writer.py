"""Tests for writers.image_writer.

Blocks here are built by hand (not through OCR) so the writer can be tested in isolation from
`readers/image_reader.py`, mirroring how it is actually invoked: it draws whatever text
currently sits on the block, translated or not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_image_fixture import (
    PATTERN_TEXT,
    PLAIN_TEXT,
    build_plain_white,
    build_text_over_pattern,
    text_bbox,
)

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Direction,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.fitting.fontmatch import missing_glyphs
from layoutkeep.writers.image_writer import _resolve_font_path, write_image

TURKISH_TEXT = "Çabuk kahverengi tilki tembel köpeğin üzerinden atlar. ĞşıİçÖü"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _make_doc(image_path: Path, *, bg: str, translated_text: str, page_source_ref: str) -> Document:
    x0, y0, x1, y1 = text_bbox(PLAIN_TEXT, 24, (30, 60))
    bbox = BBox(float(x0) - 5, float(y0) - 5, float(x1) + 5, float(y1) + 25)  # room for a longer translation
    style = Style(font_family="Arial", size=20.0, color="#000000", background=bg)
    span = Span(text=translated_text, bbox=bbox, style=style, direction=Direction.LTR)
    block = Block(id="b0", role=BlockRole.BODY, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=0)
    page = Page(number=1, width=600.0, height=150.0, blocks=[block], source_ref=page_source_ref)
    doc = Document(source_path=str(image_path), source_format="image", target_lang="tr")
    doc.pages = [page]
    return doc


def test_font_resolution_covers_turkish_glyphs() -> None:
    style = Style(font_family="Arial", size=20.0)
    path = _resolve_font_path(style, "tr")
    assert Path(path).exists()
    assert missing_glyphs(path, "ğĞşŞıİçÇöÖüÜ") == ""


def test_translated_text_drawn_over_plain_ground(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)
    doc = _make_doc(src, bg="#ffffff", translated_text=TURKISH_TEXT, page_source_ref=str(src))

    out = tmp_path / "out.png"
    write_image(doc, src, out)

    before = np.array(Image.open(src).convert("RGB"))
    after = np.array(Image.open(out).convert("RGB"))
    x0, y0, x1, y1 = text_bbox(PLAIN_TEXT, 24, (30, 60))
    box_before = before[y0 - 5 : y1 + 25, x0 - 5 : x1 + 5]
    box_after = after[y0 - 5 : y1 + 25, x0 - 5 : x1 + 5]

    # The box changed (old text gone, new text drawn) and dark ink is present again.
    assert not np.array_equal(box_before, box_after)
    assert (box_after.reshape(-1, 3).min(axis=1) < 100).any()  # some genuinely dark pixels = drawn text
    # Background elsewhere in the box stays white (the fill, not the old English glyphs).
    corner = after[y0 - 4, x0 - 4]
    assert tuple(int(c) for c in corner) == (255, 255, 255)


def test_translated_text_drawn_over_patterned_ground(tmp_path: Path) -> None:
    src = tmp_path / "pattern.png"
    build_text_over_pattern(src)
    x0, y0, x1, y1 = text_bbox(PATTERN_TEXT, 22, (30, 60))
    bbox = BBox(float(x0) - 5, float(y0) - 5, float(x1) + 5, float(y1) + 25)
    style = Style(font_family="Arial", size=18.0, color="#ffffff", background="#202020")
    span = Span(text=TURKISH_TEXT, bbox=bbox, style=style, direction=Direction.LTR)
    block = Block(id="b0", role=BlockRole.BODY, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=0)
    page = Page(number=1, width=600.0, height=150.0, blocks=[block], source_ref=str(src))
    doc = Document(source_path=str(src), source_format="image", target_lang="tr")
    doc.pages = [page]

    out = tmp_path / "out.png"
    write_image(doc, src, out)

    before = np.array(Image.open(src).convert("RGB"))
    after = np.array(Image.open(out).convert("RGB"))
    assert not np.array_equal(before, after)


def test_scanned_pdf_source_writes_a_pdf(tmp_path: Path) -> None:
    src1 = tmp_path / "page1.png"
    src2 = tmp_path / "page2.png"
    build_plain_white(src1)
    build_plain_white(src2)

    x0, y0, x1, y1 = text_bbox(PLAIN_TEXT, 24, (30, 60))
    bbox = BBox(float(x0) - 5, float(y0) - 5, float(x1) + 5, float(y1) + 25)
    style = Style(font_family="Arial", size=20.0, color="#000000", background="#ffffff")

    pages = []
    for i, src in enumerate((src1, src2)):
        span = Span(text=TURKISH_TEXT, bbox=bbox, style=style, direction=Direction.LTR)
        block = Block(id=f"b{i}", role=BlockRole.BODY, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=0)
        pages.append(Page(number=i + 1, width=600.0, height=150.0, blocks=[block], source_ref=str(src)))

    doc = Document(source_path=str(src1), source_format="pdf", target_lang="tr")
    doc.pages = pages

    out = tmp_path / "out.pdf"
    write_image(doc, src1, out)

    assert out.exists()
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF")
    # Pillow has no PDF *reader* to round-trip through, so count page objects directly - two
    # source pages in must mean two page objects out. "/Type /Pages" (the page tree root) is
    # excluded via the negative lookahead; only leaf "/Type /Page" objects are counted.
    import re

    assert len(re.findall(rb"/Type\s*/Page(?!s)", raw)) == 2


def test_non_translatable_block_is_left_untouched(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)
    x0, y0, x1, y1 = text_bbox(PLAIN_TEXT, 24, (30, 60))
    bbox = BBox(float(x0), float(y0), float(x1), float(y1))
    style = Style(font_family="Arial", size=20.0, color="#000000", background="#ffffff")
    span = Span(text="42", bbox=bbox, style=style, direction=Direction.LTR)
    block = Block(
        id="p0", role=BlockRole.PAGE_NUMBER, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=0
    )
    page = Page(number=1, width=600.0, height=150.0, blocks=[block], source_ref=str(src))
    doc = Document(source_path=str(src), source_format="image", target_lang="tr")
    doc.pages = [page]

    out = tmp_path / "out.png"
    write_image(doc, src, out)

    before = np.array(Image.open(src).convert("RGB"))
    after = np.array(Image.open(out).convert("RGB"))
    assert np.array_equal(before, after)
