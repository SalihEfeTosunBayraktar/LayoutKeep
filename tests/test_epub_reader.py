"""Unit tests for epub_reader.read_epub against the fixture EPUB."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.core.docir import BlockRole
from layoutkeep.readers.epub_reader import read_epub


def _read(tmp_path: Path):
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    return read_epub(src)


def test_two_pages_in_spine_order(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    assert [p.source_ref for p in doc.pages] == ["chap1.xhtml", "chap2.xhtml"]


def test_source_lang_from_opf(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    assert doc.source_lang == "en"


def test_block_order_is_monotonic(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    for page in doc.pages:
        orders = [b.order for b in page.blocks_in_reading_order()]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)


def test_roles(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    chap1 = doc.pages[0]
    by_text = {b.text: b for b in chap1.blocks}

    assert by_text["Chapter One"].role == BlockRole.TITLE
    assert by_text["First item"].role == BlockRole.LIST
    assert by_text["This is the footnote text referenced above."].role == BlockRole.BODY

    code_block = next(b for b in chap1.blocks if "def add" in b.text)
    assert code_block.role == BlockRole.CODE

    chap2 = doc.pages[1]
    heading = next(b for b in chap2.blocks if b.text == "Chapter Two")
    assert heading.role == BlockRole.HEADING
    cell = next(b for b in chap2.blocks if b.text == "Row one, cell one")
    assert cell.role == BlockRole.TABLE
    inline_code = next(b for b in chap2.blocks if b.text == "x = 1")
    assert inline_code.role == BlockRole.CODE


def test_inline_bold_italic_spans(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    chap1 = doc.pages[0]
    block = next(b for b in chap1.blocks if "bold" in b.text and "italic" in b.text)
    spans = block.lines[0].spans
    styles = [(s.text, s.style.bold, s.style.italic) for s in spans]
    assert ("bold", True, False) in styles
    assert ("italic", False, True) in styles
    # surrounding plain text stays unbolded/unitalicised
    assert any(text == "This is a " and not bold and not italic for text, bold, italic in styles)


def test_image_alt_and_title_become_caption_blocks(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    chap1 = doc.pages[0]
    alt_block = next(b for b in chap1.blocks if b.text == "A cover picture")
    title_block = next(b for b in chap1.blocks if b.text == "Cover")
    assert alt_block.role == BlockRole.CAPTION
    assert title_block.role == BlockRole.CAPTION
    assert alt_block.id.endswith(":alt")
    assert title_block.id.endswith(":title")


def test_non_translatable_roles_excluded_from_segments(tmp_path: Path) -> None:
    from layoutkeep.core.docir import segments_from_document

    doc = _read(tmp_path)
    segments = segments_from_document(doc)
    sources = [s.source for s in segments]
    assert "def add(a, b):\n    return a + b" not in sources
    assert "x = 1" not in sources
