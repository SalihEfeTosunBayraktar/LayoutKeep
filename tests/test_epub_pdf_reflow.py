"""Tests for EPUB→PDF reflow: chapter page-breaks and image extraction.

These pin down the two defects that surfaced from real books: MuPDF's `layout()` ignored
`page-break-before` so chapter headings landed mid-page, and the EPUB reader ignored pictures so
a rebuilt PDF lost its figures.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.writers.pdf_generator import generate_reflowed_pdf_from_docir


def test_epub_reader_extracts_images(tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    doc = read_epub(src)
    images = [img for page in doc.pages for img in page.images]
    assert len(images) == 1
    assert images[0].fmt == "png"
    # the fixture's cover.png bytes, base64-decoded, must round-trip
    assert base64.b64decode(images[0].data).startswith(b"\x89PNG")


def _block(text: str, role: BlockRole, size: float) -> Block:
    return Block(
        id=f"{role.value}::{text[:8]}",
        role=role,
        bbox=BBox(0, 0, 0, 0),
        lines=[Line(spans=[Span(text=text, bbox=BBox(0, 0, 0, 0), style=Style(size=size))])],
        order=0,
    )


def test_reflow_starts_each_chapter_on_a_new_page(tmp_path: Path) -> None:
    doc = Document(source_path="x.epub", source_format="epub")
    doc.pages = [
        Page(
            number=1,
            width=0.0,
            height=0.0,
            blocks=[
                _block("intro paragraph with enough text to fill some space " * 20, BlockRole.BODY, 12.0),
                _block("CHAPTER I", BlockRole.HEADING, 18.0),
                _block("chapter one body " * 30, BlockRole.BODY, 12.0),
                _block("CHAPTER II", BlockRole.HEADING, 18.0),
                _block("chapter two body " * 30, BlockRole.BODY, 12.0),
            ],
        )
    ]
    out = tmp_path / "reflow.pdf"
    generate_reflowed_pdf_from_docir(doc, out)

    pdf = pymupdf.open(str(out))
    chapter_pages: dict[str, int] = {}
    for pno in range(pdf.page_count):
        text = pdf[pno].get_text()
        if "CHAPTER I" in text and "CHAPTER I" not in chapter_pages:
            chapter_pages["CHAPTER I"] = pno
        if "CHAPTER II" in text:
            chapter_pages["CHAPTER II"] = pno
    assert "CHAPTER I" in chapter_pages and "CHAPTER II" in chapter_pages
    # The two chapter headings must be on different pages (page-break enforced).
    assert chapter_pages["CHAPTER I"] != chapter_pages["CHAPTER II"]
