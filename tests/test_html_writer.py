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


def _table_cell(text: str, row: int, col: int, table_id: int = 0) -> Block:
    dummy_style = Style()
    return Block(
        id=f"t{table_id}r{row}c{col}",
        role=BlockRole.TABLE,
        bbox=BBox(0, 0, 10, 10),
        lines=[Line(spans=[Span(text=text, bbox=BBox(0, 0, 10, 10), style=dummy_style)])],
        table_id=table_id,
        table_row=row,
        table_col=col,
    )


def test_table_cells_become_a_real_table(tmp_path: Path) -> None:
    """`table_row`/`table_col` (core/docir.py) exist so a rebuilt table is a grid again, not
    one paragraph per cell (docs/ENGINE-ARCHITECTURE.md) - measured on rich_report.pdf, whose
    4x4 table came out as sixteen separate `<p>` tags before this."""
    doc = Document(source_path="test.pdf", source_format="pdf", target_lang="en")
    page = Page(number=1, width=0.0, height=0.0, source_ref="p1")
    page.blocks = [
        _table_cell("Cell", 0, 0), _table_cell("Status", 0, 1),
        _table_cell("A-101", 1, 0), _table_cell("Pass", 1, 1),
    ]
    doc.pages = [page]

    out_path = tmp_path / "table.html"
    write_html(doc, Path("test.pdf"), out_path)
    content = out_path.read_text(encoding="utf-8")

    assert content.count("<table>") == 1
    assert content.count("<tr>") == 2
    # Reading order left to right, top to bottom - not the order the blocks were appended in.
    first_row = content.split("<tr>")[1].split("</tr>")[0]
    assert first_row.index("Cell") < first_row.index("Status")


def test_a_table_role_block_without_a_grid_position_stays_a_paragraph(tmp_path: Path) -> None:
    """epub_reader.py and docx_reader.py assign BlockRole.TABLE but do not (yet) fill
    table_row/table_col - both default to -1. Grouping by position regardless found and lost
    real content: every untagged cell landed at grid position (-1, -1) and collapsed a whole
    table down to its last cell (rendering rich_book.epub->html for real, not by a metric,
    dropped a 5-cell table to 1). This is the regression test for that."""
    cell_a = _table_cell("Row one", 0, 0)
    cell_a.table_row = -1
    cell_a.table_col = -1
    cell_b = _table_cell("Row two", 1, 0)
    cell_b.table_row = -1
    cell_b.table_col = -1

    doc = Document(source_path="test.epub", source_format="epub", target_lang="en")
    page = Page(number=1, width=0.0, height=0.0, source_ref="p1")
    page.blocks = [cell_a, cell_b]
    doc.pages = [page]

    out_path = tmp_path / "untagged.html"
    write_html(doc, Path("test.epub"), out_path)
    content = out_path.read_text(encoding="utf-8")

    assert "<table>" not in content
    assert "Row one" in content
    assert "Row two" in content


def test_two_tables_on_one_page_stay_separate(tmp_path: Path) -> None:
    """Two distinct `table_id`s must produce two `<table>` elements, not one eight-cell grid."""
    doc = Document(source_path="test.pdf", source_format="pdf", target_lang="en")
    page = Page(number=1, width=0.0, height=0.0, source_ref="p1")
    page.blocks = [
        _table_cell("A", 0, 0, table_id=0), _table_cell("B", 0, 1, table_id=0),
        _table_cell("X", 0, 0, table_id=1), _table_cell("Y", 0, 1, table_id=1),
    ]
    doc.pages = [page]

    out_path = tmp_path / "two_tables.html"
    write_html(doc, Path("test.pdf"), out_path)
    content = out_path.read_text(encoding="utf-8")

    assert content.count("<table>") == 2
