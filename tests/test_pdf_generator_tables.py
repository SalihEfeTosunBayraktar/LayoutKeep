"""A table must reach a generated PDF as a real table, not one paragraph per cell.

Found opening a real docx->pdf output next to its source (not by a metric): the table's cells
came out as flowing paragraphs stacked one under another, in reading order, with every row/column
relationship gone. `html_writer.py` got the same fix (real `<table>` from `table_row`/`table_col`,
core/docir.py) in the same session; this is the identical gap in `_draw_flowing_page`, which
iterated blocks individually and had no notion of a table at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.writers.pdf_generator import generate_pdf_from_docir


def _table_cell(text: str, row: int, col: int, table_id: int = 0) -> Block:
    return Block(
        id=f"t{table_id}r{row}c{col}",
        role=BlockRole.TABLE,
        bbox=BBox(0, 0, 10, 10),
        lines=[Line(spans=[Span(text=text, bbox=BBox(0, 0, 10, 10), style=Style())])],
        table_id=table_id,
        table_row=row,
        table_col=col,
    )


def test_table_cells_become_a_real_table(tmp_path: Path) -> None:
    page = Page(
        number=1,
        width=0,
        height=0,
        blocks=[
            _table_cell("Cell", 0, 0), _table_cell("Status", 0, 1),
            _table_cell("A-101", 1, 0), _table_cell("Pass", 1, 1),
        ],
        source_ref="0",
    )
    doc = Document(pages=[page])

    out = tmp_path / "out.pdf"
    generate_pdf_from_docir(doc, out)

    with pymupdf.open(out) as pdf:
        tables = pdf[0].find_tables()
        assert len(tables.tables) == 1, "MuPDF should detect one real table on the page"
        rows = tables.tables[0].extract()
        assert rows[0][0] == "Cell"
        assert rows[0][1] == "Status"
        assert rows[1][0] == "A-101"
        assert rows[1][1] == "Pass"


def test_a_table_block_without_a_grid_position_stays_a_paragraph(tmp_path: Path) -> None:
    """docx_reader.py and pdf_reader.py fill table_row/table_col; epub_reader.py does not yet
    and leaves both at -1. Grouping by position regardless would put every one of its cells at
    grid position (-1, -1) and silently drop all but the last (html_writer.py hit exactly this
    regression - see its own guard and regression test)."""
    cell_a = _table_cell("Row one", 0, 0)
    cell_a.table_row = -1
    cell_a.table_col = -1
    cell_b = _table_cell("Row two", 1, 0)
    cell_b.table_row = -1
    cell_b.table_col = -1

    page = Page(number=1, width=0, height=0, blocks=[cell_a, cell_b], source_ref="0")
    doc = Document(pages=[page])

    out = tmp_path / "out.pdf"
    generate_pdf_from_docir(doc, out)

    with pymupdf.open(out) as pdf:
        assert len(pdf[0].find_tables().tables) == 0
        text = pdf[0].get_text()
    assert "Row one" in text
    assert "Row two" in text
