"""A translation that needs a second line may use the room the page has, not just the writer's slack.

Measured on the first real run after the campaign (arXiv 2507.03009, gemma-4-e4b): one table page
came back `fitting 70 blocks: shrunk=42 overflow=28`, an author-list page `3 blocks: overflow=3`,
and on the NASA scan's first page four of six overflowing blocks had 31-39 pt of empty paper below
them. `room_below` cannot help there - it returns at most the writer's 3 pt slack, so it never says
"the page has room", only "how much of the slack is free".

These tests hold `fitting/growth.free_below` and the fitting decision it feeds.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Segment, Span, Style
from layoutkeep.fitting.fit import FitLayer, FitMode, fit_segment
from layoutkeep.fitting.growth import free_below


def _block(block_id: str, y0: float, y1: float, text: str = "Some English text here") -> Block:
    bbox = BBox(50.0, y0, 250.0, y1)
    span = Span(text=text, bbox=bbox, style=Style(font_family="Arial", size=10.0))
    return Block(
        id=block_id, role=BlockRole.BODY, bbox=bbox, lines=[Line(spans=[span], bbox=bbox)], order=1
    )


def test_the_gap_to_the_next_block_is_what_can_be_granted() -> None:
    above = _block("b1", 100.0, 112.0)
    below = _block("b2", 140.0, 152.0)

    granted = free_below(above, [above, below], limit=60.0)

    # 28 pt of gap, 2 pt kept back.
    assert granted == 26.0


def test_a_tight_gap_grants_nothing() -> None:
    above = _block("b1", 100.0, 112.0)
    touching = _block("b2", 113.0, 125.0)
    overlapping = _block("b3", 90.0, 130.0)  # OCR boxes overlap; nothing is free above the next

    assert free_below(above, [above, touching], limit=60.0) == 0.0
    assert free_below(above, [above, overlapping], limit=60.0) == 0.0


def test_the_grant_is_capped_by_the_limit() -> None:
    above = _block("b1", 100.0, 112.0)
    far_below = _block("b2", 400.0, 412.0)

    assert free_below(above, [above, far_below], limit=18.0) == 16.0


def test_another_column_does_not_bound_the_grant() -> None:
    left = _block("b1", 100.0, 112.0)
    right = _block("b2", 120.0, 140.0)
    right.bbox = BBox(400.0, 120.0, 500.0, 140.0)

    # The right column does not bound it (40 - the 2 pt kept back).
    assert free_below(left, [left, right], limit=40.0) == 38.0


def test_a_picture_below_stops_the_grant() -> None:
    """A figure OCR found no text in is not a block, and growing across it would draw the
    translation over the drawing."""
    above = _block("b1", 100.0, 112.0)
    picture = BBox(40.0, 130.0, 300.0, 260.0)

    # The picture's top is 18 pt below; 2 pt of that stays.
    assert free_below(above, [above], limit=60.0, obstacles=[picture]) == 16.0


def _segment(source: str, target: str) -> Segment:
    return Segment(block_id="b1", source=source, target=target, max_len=None)


def _fits(bbox: BBox) -> FitLayer:
    from layoutkeep.writers.pdf_writer import measure_fit

    style = Style(font_family="Arial", size=10.0)
    result = fit_segment(
        _segment("A single English line of about nine words.", "Tek satırlık çeviri çok daha uzun bir metne dönüşür burada."),
        style,
        bbox,
        measure_fit,
        mode=FitMode.STRICT,
        retranslate=None,
        char_budget=None,
        rotation=0,
    )
    return result.layer


def test_a_second_line_fits_once_the_page_room_is_granted() -> None:
    tight = BBox(50.0, 100.0, 250.0, 112.0)
    granted = BBox(50.0, 100.0, 250.0, 112.0 + 18.0)

    assert _fits(tight) is FitLayer.OVERFLOW
    assert _fits(granted) is FitLayer.AS_IS


def test_a_running_header_or_title_keeps_its_one_line_box() -> None:
    """Wrapping a header changes the shape of the page; the full suite caught exactly that
    (`test_page_number_and_header_survive_untouched`) when the grant first reached one."""
    from layoutkeep.fitting.growth import may_grow

    assert may_grow(_block("b1", 100.0, 112.0))
    for role in (BlockRole.HEADING, BlockRole.TITLE, BlockRole.HEADER, BlockRole.FOOTER,
                 BlockRole.PAGE_NUMBER):
        block = _block("b1", 100.0, 112.0)
        block.role = role
        assert not may_grow(block), role
