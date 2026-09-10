"""Unit tests for docx_reader.read_docx against the fixture DOCX."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_docx_fixture import build_sample_docx

from layoutkeep.core.docir import BlockRole
from layoutkeep.readers.docx_reader import read_docx


def _read(tmp_path: Path):
    src = tmp_path / "sample.docx"
    build_sample_docx(src)
    return read_docx(src)


def test_pages_cover_body_header_footer_footnotes(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    refs = [p.source_ref for p in doc.pages]
    assert refs == [
        "word/document.xml",
        "word/footer1.xml",
        "word/header1.xml",
        "word/footnotes.xml",
    ]


def test_source_lang_from_core_xml(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    assert doc.source_lang == "en-US"


def test_block_order_is_monotonic(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    for page in doc.pages:
        orders = [b.order for b in page.blocks_in_reading_order()]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)


def test_roles(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    body = doc.pages[0]
    by_text = {b.text: b for b in body.blocks}

    assert by_text["Sample Document Title"].role == BlockRole.TITLE
    assert by_text["Section One"].role == BlockRole.HEADING
    assert by_text["First item"].role == BlockRole.LIST
    assert by_text["Second item"].role == BlockRole.LIST
    assert by_text["Row one, cell one"].role == BlockRole.TABLE
    assert by_text["Row one, cell two"].role == BlockRole.TABLE

    header = doc.pages[2]
    assert header.source_ref == "word/header1.xml"
    assert all(b.role == BlockRole.HEADER for b in header.blocks)

    footer = doc.pages[1]
    assert footer.source_ref == "word/footer1.xml"
    assert all(b.role == BlockRole.FOOTER for b in footer.blocks)

    footnotes = doc.pages[3]
    assert footnotes.source_ref == "word/footnotes.xml"
    assert all(b.role == BlockRole.FOOTNOTE for b in footnotes.blocks)
    assert any("footnote text" in b.text for b in footnotes.blocks)


def test_inline_bold_italic_spans(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if "bold" in b.text and "italic" in b.text)
    spans = block.lines[0].spans
    styles = [(s.text, s.style.bold, s.style.italic) for s in spans]
    assert ("bold", True, False) in styles
    assert ("italic", False, True) in styles
    assert any(text == "This is a " and not bold and not italic for text, bold, italic in styles)


def test_split_runs_merge_into_one_plain_span(tmp_path: Path) -> None:
    """"This is a " and " word and an " were written as separate <w:r> runs sharing the same
    (no bold, no italic) style - they must merge, not arrive as separate marker candidates."""
    doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if "bold" in b.text and "italic" in b.text)
    plain_spans = [s for s in block.lines[0].spans if not s.style.bold and not s.style.italic]
    assert len(plain_spans) == 3  # "This is a ", " word and an ", " word."


def test_hyperlink_text_present(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if "our website" in b.text)
    assert block.text == "Visit our website for more."


def test_footnote_reference_paragraph_has_no_stray_marker_text(tmp_path: Path) -> None:
    doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if "This has a footnote" in b.text)
    assert block.text == "This has a footnote."
