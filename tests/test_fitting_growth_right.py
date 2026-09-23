"""A line whose translation runs longer than the source's line may use the page's free space to the right.

WHY: the reader records the *tight glyph box* of a line, so a heading is only as wide as its own
letters. English runs wider than Turkish on the recorded TR->EN bench (measured: 1.11x, 1.30x,
1.09x target/source by characters on `tr_tck_5237` and `tr_kalkinma_12`), and the translation then
wraps into a second line the one-line box has no height for. `free_below` cannot help - a margin
heading sits directly above the article text, so there is no room below - and the fit shrinks the
text to the floor or flags it. Measured on the four recorded runs: 42 blocks were flagged, and 28
of them fit at their own size once the box may reach the free space beside them.

The room is bounded, not guessed: by the page's own content edge (the rightmost point any block on
the page reaches, so a full-width paragraph gets nothing and a two-column page cannot grow across
its gutter), by every neighbour whose rows overlap the block's, and by a tunable. This is the
horizontal twin of `fitting/growth.free_below`, and the fitting pass and the writer read the same
number - a box measured one way and drawn another is how a block ends up shrunk twice.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Segment,
    Span,
    Style,
    apply_segments,
    segments_from_document,
)
from layoutkeep.fitting.fit import FitLayer
from layoutkeep.fitting.growth import free_right
from layoutkeep.fitting.pdf_pass import fit_pdf_pass
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf


def _block(block_id: str, x0: float, x1: float, y0: float, y1: float,
           text: str = "Some English text here") -> Block:
    bbox = BBox(x0, y0, x1, y1)
    span = Span(text=text, bbox=bbox, style=Style(font_family="Arial", size=10.0))
    return Block(
        id=block_id, role=BlockRole.BODY, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=1
    )


# --------------------------------------------------------------------------------------
# The rule itself
# --------------------------------------------------------------------------------------


def test_a_short_line_may_reach_the_pages_own_content_edge() -> None:
    """The page's rightmost block is what the column's edge is; nothing else is assumed."""
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    paragraph = _block("b2", 50.0, 520.0, 300.0, 312.0)

    # 370 pt of paper to the right of the heading, 2 pt kept back.
    assert free_right(heading, [heading, paragraph], limit=1000.0) == 368.0


def test_a_full_width_paragraph_is_granted_nothing() -> None:
    paragraph = _block("b1", 50.0, 520.0, 100.0, 112.0)
    other = _block("b2", 50.0, 520.0, 300.0, 312.0)

    assert free_right(paragraph, [paragraph, other], limit=1000.0) == 0.0


def test_a_neighbour_in_the_same_rows_bounds_the_grant() -> None:
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    beside = _block("b2", 300.0, 500.0, 104.0, 120.0)

    # The neighbour starts at 300: 150 pt of gap, 2 pt kept back.
    assert free_right(heading, [heading, beside], limit=1000.0) == 148.0


def test_a_neighbour_in_another_band_does_not_bound_it() -> None:
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    above = _block("b2", 300.0, 500.0, 60.0, 80.0)
    below = _block("b3", 300.0, 500.0, 140.0, 160.0)

    # The column edge is 500; neither neighbour shares a row with the heading.
    assert free_right(heading, [heading, above, below], limit=1000.0) == 348.0


def test_a_neighbour_that_starts_inside_the_block_owns_the_space() -> None:
    """A paragraph the block sits beside reaches past it: growing into it would draw over it."""
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    paragraph = _block("b2", 100.0, 500.0, 100.0, 130.0)

    assert free_right(heading, [heading, paragraph], limit=1000.0) == 0.0


def test_a_picture_to_the_right_stops_the_grant() -> None:
    """A figure OCR found no text in is not a block, and growing across it would draw on it."""
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    paragraph = _block("b2", 50.0, 520.0, 300.0, 312.0)
    picture = BBox(300.0, 90.0, 500.0, 160.0)

    assert free_right(heading, [heading, paragraph], limit=1000.0, obstacles=[picture]) == 148.0


def test_a_table_cell_may_not_pass_the_next_columns_content() -> None:
    """A wrapped cell leaves its row empty beside it, so the band bound alone would let it leave.

    Measured on `tr_kalkinma_12` p2: the ruled table's "Ratio of Planned Industrial Areas ... to
    Country Area" cell is one line of a two-line cell, the row beside it holds nothing, and with the
    page's edge as its bound the renderer drew the line at full size with its last word 4 pt past
    the column's rule.
    """
    cell = _block("b1", 50.0, 150.0, 100.0, 112.0)
    cell.role = BlockRole.TABLE
    same_row_other_column = _block("b2", 300.0, 500.0, 60.0, 80.0)
    paragraph = _block("b3", 50.0, 520.0, 300.0, 312.0)

    # The next column's content starts at 300: 150 pt of gap, 2 pt kept back.
    assert free_right(cell, [cell, same_row_other_column, paragraph], limit=1000.0) == 148.0


def test_a_table_cell_still_gets_its_own_columns_room() -> None:
    """The rule is the cell's column, not "no room at all": a tight box inside a wide column grows."""
    cell = _block("b1", 50.0, 150.0, 100.0, 112.0)
    cell.role = BlockRole.TABLE
    neighbour_column = _block("b2", 260.0, 400.0, 60.0, 80.0)

    assert free_right(cell, [cell, neighbour_column], limit=1000.0) == 108.0


def test_the_grant_is_capped_by_the_limit() -> None:
    heading = _block("b1", 50.0, 150.0, 100.0, 112.0)
    paragraph = _block("b2", 50.0, 520.0, 300.0, 312.0)

    assert free_right(heading, [heading, paragraph], limit=18.0) == 16.0


# --------------------------------------------------------------------------------------
# The fitting pass
# --------------------------------------------------------------------------------------

#: A heading that is one line tall on a page whose column runs to 520 - the shape of the Turkish
#: Penal Code's margin headings (`tr_tck_5237` p1: 'Ceza Kanununun amacı' in an 89x10 pt box).
_HEADING = "Ceza Kanununun amacı"
_HEADING_EN = "The purpose of the Penal Code"


def _doc_with_heading(align: str = "left") -> Document:
    heading = _block("h", 50.0, 150.0, 100.0, 112.0, text=_HEADING)
    heading.role = BlockRole.HEADING
    heading.align = align
    heading.source_text = _HEADING
    paragraph = _block("p", 50.0, 520.0, 300.0, 312.0, text="The article itself sits well below.")
    paragraph.source_text = "Maddenin kendisi çok aşağıda durur."
    return Document(
        source_lang="tr",
        target_lang="en",
        pages=[Page(number=1, width=595, height=842, blocks=[heading, paragraph])],
    )


def _fit(doc: Document, target: str) -> list:
    segments = [
        Segment(block_id="h", source=_HEADING, target=target),
        Segment(block_id="p", source="Maddenin kendisi çok aşağıda durur.",
                target="The article itself sits well below."),
    ]
    results = []
    fit_pdf_pass(
        doc, segments, retranslate=lambda seg, _budget: seg.target,
        target_lang="en", on_fitted=lambda _s, _b, r: results.append(r),
    )
    return results


def test_a_heading_that_runs_longer_keeps_its_one_line() -> None:
    """The measured case: 29 characters of English in a 100 pt box with 370 pt of free paper."""
    doc = _doc_with_heading()

    results = _fit(doc, _HEADING_EN)

    assert results[0].layer is FitLayer.AS_IS, results[0]
    assert not results[0].needs_review


def test_the_room_to_the_right_is_what_the_fit_measures_against() -> None:
    """Closing the tunable must bring the old verdict back, or the rule is not what decided it."""
    from layoutkeep.core import tunables

    tunables.set_value("write.grant_room_right_pt", 0.0)
    try:
        doc = _doc_with_heading()
        results = _fit(doc, _HEADING_EN)
    finally:
        tunables.reset("write.grant_room_right_pt")

    assert results[0].layer is FitLayer.OVERFLOW
    assert results[0].needs_review


def test_a_centred_block_keeps_its_box() -> None:
    """Widening a centred box moves the text, because the writer centres inside the box."""
    doc = _doc_with_heading(align="center")

    results = _fit(doc, _HEADING_EN)

    assert results[0].layer is FitLayer.OVERFLOW


def test_a_table_cell_that_overflows_its_column_is_still_flagged() -> None:
    """A column is a fixed width: a longer translation inside one wraps or shrinks, never leaves.

    Measured on `tr_kalkinma_12` p2: the ruled table's "Ratio of Planned Industrial Areas ... to
    Country Area" cell fills its box to the last point, and with the page's edge as its bound the
    renderer drew the line at full size and the last word crossed the column's rule by 4 pt.
    """
    doc = _doc_with_heading()
    blocks = doc.pages[0].blocks
    cell = next(b for b in blocks if b.id == "h")
    cell.role = BlockRole.TABLE
    # The next column's content begins right after the cell, and the row below is tight.
    blocks.append(_block("c", 151.5, 300.0, 60.0, 72.0, text="2022"))
    next(b for b in blocks if b.id == "p").bbox = BBox(50.0, 118.0, 520.0, 130.0)

    results = _fit(doc, _HEADING_EN)

    assert results[0].layer is FitLayer.OVERFLOW
    assert results[0].needs_review


# --------------------------------------------------------------------------------------
# The writer
# --------------------------------------------------------------------------------------


def _page_with_heading(path: Path) -> None:
    """A short one-line heading whose English is twice as wide, on a page with free paper beside it.

    The shape of `tr_tck_5237` p1: the Turkish Penal Code's margin headings are one line each and
    the article text sits directly under them, so nothing can be granted below.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 110), "Ceza Kanunu", fontname="helv", fontsize=9)
    page.insert_text((50, 310), "Maddenin kendisi cok asagida durur.", fontname="helv", fontsize=9)
    doc.save(str(path))


def _written_words(out: Path) -> list[tuple[float, float, str]]:
    with pymupdf.open(out) as result:
        return [(round(w[1], 1), round(w[2], 1), w[4]) for w in result[0].get_text("words")]


def test_the_writer_draws_the_widened_line_on_one_line(tmp_path: Path) -> None:
    """The fit and the writer must agree: a box measured wide and drawn narrow shrinks twice."""
    src = tmp_path / "src.pdf"
    _page_with_heading(src)
    doc = read_pdf(src)
    heading = next(b for _p, b in doc.iter_blocks() if "Ceza" in b.text)
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = _HEADING_EN if "Ceza" in seg.source else "The article itself sits well below."
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    words = _written_words(out)
    band = {y for y, _x1, word in words if word == "purpose"}
    assert band, f"the heading disappeared: {words}"
    drawn = [(y, x1) for y, x1, _word in words if y in band]
    assert len(band) == 1, f"the heading wrapped: {drawn}"
    # It reached past the source line's own box, so the room beside it was used.
    assert max(x1 for _y, x1 in drawn) > heading.bbox.x1 + 3.0
