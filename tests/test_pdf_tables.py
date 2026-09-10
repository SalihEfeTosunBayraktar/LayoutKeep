"""A table has to come out of translation as a table.

The project's own comparison image was showing the defect: a 5x3 table arrived as one block
whose text was every cell joined together, so the translation went into the first cell's box and
the rest of the table came out empty. The numbers survived - the protected-value mechanism works
- and the structure did not, which is the one thing this project claims to keep.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from layoutkeep.readers.pdf_reader import read_pdf

SAMPLE = Path(__file__).resolve().parent.parent / "docs" / "samples" / "sample_report.pdf"

HEADER = ("Plate", "Cycles", "Deflection")
FIRST_ROW = ("A-1", "10", "0.42 mm")


@pytest.fixture(scope="module")
def blocks():
    if not SAMPLE.exists():
        pytest.skip("sample document not generated")
    return [b for _, b in read_pdf(SAMPLE).iter_blocks()]


def _cell(blocks, text: str):
    return next((b for b in blocks if b.text.strip() == text), None)


def test_every_cell_is_its_own_block(blocks) -> None:
    for text in HEADER + FIRST_ROW:
        assert _cell(blocks, text) is not None, f"{text!r} is not a block of its own"


def test_a_row_is_not_read_as_a_paragraph(blocks) -> None:
    """MuPDF hands the header row over as one block of three side-by-side lines. Read as a
    paragraph it becomes "Plate Cycles Deflection" in one box."""
    joined = [b for b in blocks if b.text.count("\n") >= 2 and "Plate" in b.text]

    assert joined == [], f"cells merged into {[b.text for b in joined]}"


def test_the_cells_keep_the_geometry_of_the_table(blocks) -> None:
    """Each cell has to carry its own box, or the writer has nowhere to put the translation."""
    header = [_cell(blocks, text) for text in HEADER]
    first = [_cell(blocks, text) for text in FIRST_ROW]

    # A row shares a baseline.
    assert len({round(b.bbox.y0) for b in header}) == 1
    # A column shares a left edge - within a point, which is what a table looks like.
    for above, below in zip(header, first, strict=True):
        assert abs(above.bbox.x0 - below.bbox.x0) < 1.0
    # And the cells are in reading order left to right.
    assert [b.bbox.x0 for b in header] == sorted(b.bbox.x0 for b in header)


def test_a_paragraph_is_still_one_block(blocks) -> None:
    """The fix must not turn body text into fragments: the wrapped lines of a paragraph are
    still one block, and the two-column body still reads as two columns."""
    abstract = next(b for b in blocks if b.text.startswith("This report summarises"))

    assert abstract.text.count("\n") >= 2, "wrapped lines were split apart"
    assert "cyclic heating" in abstract.text
