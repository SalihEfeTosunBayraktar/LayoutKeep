"""Tests for layoutkeep.writers.html_writer."""

from __future__ import annotations

from pathlib import Path

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.writers.html_writer import write_html


def test_write_html_generates_valid_html5(tmp_path: Path) -> None:
    # Basit bir DocIR oluşturur / Creates a simple DocIR document
    doc = Document(source_path="test.epub", source_format="epub", target_lang="tr")
    doc.metadata["title"] = "Test Belgesi"

    page = Page(number=1, width=0.0, height=0.0, source_ref="chap_001.xhtml")
    dummy_style = Style()
    title_block = Block(
        id="b1",
        role=BlockRole.TITLE,
        bbox=BBox(0, 0, 100, 20),
        lines=[Line(spans=[Span(text="Merhaba Dunya", bbox=BBox(0, 0, 100, 20), style=dummy_style)])],
    )
    p_block = Block(
        id="b2",
        role=BlockRole.BODY,
        bbox=BBox(0, 25, 100, 45),
        lines=[Line(spans=[Span(text="Bu bir paragraftir.", bbox=BBox(0, 25, 100, 45), style=dummy_style)])],
    )
    page.blocks = [title_block, p_block]
    doc.pages = [page]

    out_path = tmp_path / "output.html"
    write_html(doc, Path("test.epub"), out_path)

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert '<html lang="tr">' in content
    assert "<title>Test Belgesi</title>" in content
    assert "<h1>Merhaba Dunya</h1>" in content
    assert "<p>Bu bir paragraftir.</p>" in content
