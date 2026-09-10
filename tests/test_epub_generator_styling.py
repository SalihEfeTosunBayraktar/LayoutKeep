"""The EPUB generator has to carry emphasis, because emphasis is not decoration.

Measured before this existed (`tools/audit/format_matrix.py`, written up in
docs/ENGINE-ARCHITECTURE.md): `sample_report.pdf` reaches DocIR with ten runs marked bold or
italic - a bold title, an italic subtitle, bold section headings - and the EPUB produced from it
contained zero of them. Not a tag, not a CSS declaration. The information arrived at the writer
and the writer dropped it.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.writers.epub_generator import generate_epub_from_docir


def _span(text: str, *, bold: bool = False, italic: bool = False) -> Span:
    return Span(text=text, bbox=BBox(0, 0, 10, 10), style=Style(bold=bold, italic=italic))


def _document(spans: list[Span]) -> Document:
    line = Line(spans=spans, bbox=BBox(0, 0, 100, 12))
    block = Block(id="b1", role=BlockRole.BODY, bbox=BBox(0, 0, 100, 12), lines=[line])
    return Document(pages=[Page(number=1, width=200, height=200, blocks=[block], source_ref="0")])


def _xhtml_of(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.endswith((".xhtml", ".html"))
        )


def test_bold_and_italic_reach_the_epub(tmp_path: Path) -> None:
    doc = _document([
        _span("plain "),
        _span("bold", bold=True),
        _span(" and "),
        _span("italic", italic=True),
    ])
    out = tmp_path / "styled.epub"
    generate_epub_from_docir(doc, out)

    body = _xhtml_of(out)
    assert re.search(r"<(b|strong)\b[^>]*>bold</\1>", body), body
    assert re.search(r"<(i|em)\b[^>]*>italic</\1>", body), body
    assert "plain" in body


def test_a_run_that_is_both_is_marked_both(tmp_path: Path) -> None:
    out = tmp_path / "both.epub"
    generate_epub_from_docir(_document([_span("loud", bold=True, italic=True)]), out)

    body = _xhtml_of(out)
    assert "loud" in body
    assert re.search(r"<(b|strong)\b", body) and re.search(r"<(i|em)\b", body), body


def test_unstyled_text_gains_no_markup(tmp_path: Path) -> None:
    """Wrapping everything in <span> would technically pass the tests above and produce a worse
    document than the one this replaces."""
    out = tmp_path / "plain.epub"
    generate_epub_from_docir(_document([_span("nothing special here")]), out)

    body = _xhtml_of(out)
    assert "nothing special here" in body
    assert not re.search(r"<(b|strong|i|em)\b", body), body


def test_the_text_is_escaped_not_injected(tmp_path: Path) -> None:
    """Styling per span means building markup per span, which is where escaping gets lost."""
    out = tmp_path / "escape.epub"
    generate_epub_from_docir(_document([_span("a < b & c", bold=True)]), out)

    body = _xhtml_of(out)
    assert "a &lt; b &amp; c" in body
