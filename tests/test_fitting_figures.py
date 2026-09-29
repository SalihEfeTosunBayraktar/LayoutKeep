"""Blocks that share a band with a figure get a narrower box, on real geometry.

The Wikipedia case that started this: a block reported as (209, 148, 478, 257) sharing its top
lines with a picture at (362, 45, 550, 199). Those coordinates are used here as they were measured,
so the test fails if the rule stops handling the shape that produced 87 words of Turkish on top of
a photograph of a printing press.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, ImageRef, Line, Span, Style
from layoutkeep.fitting.figures import keep_off_figures, keep_page_off_figures


def _block(bbox: tuple[float, float, float, float], text: str = "Gutenberg integrated these four") -> Block:
    box = BBox(*bbox)
    span = Span(text=text, bbox=box, style=Style(size=10.0))
    return Block(id="b1", role=BlockRole.BODY, bbox=box, lines=[Line(spans=[span], bbox=box)])


def _figure(bbox: tuple[float, float, float, float]) -> ImageRef:
    return ImageRef(bbox=BBox(*bbox))


def test_a_box_is_narrowed_away_from_a_figure_beside_it():
    block = _block((209, 148, 478, 257))
    figure = _figure((362, 45, 550, 199))  # shares y 148-199 with the block, on its right

    assert keep_off_figures(block, [figure])

    assert block.bbox.x1 <= 362
    assert block.bbox.x0 == 209  # the left edge, where the source's text starts, does not move
    assert block.bbox.y0 == 148 and block.bbox.y1 == 257


def test_the_writers_slack_is_kept_out_of_the_strip():
    """The writer adds its own room to the right; the strip must leave space for it."""
    block = _block((209, 148, 478, 257))
    figure = _figure((362, 45, 550, 199))

    keep_off_figures(block, [figure], clearance=3.0)

    assert block.bbox.x1 <= 362 - 3.0


def test_a_figure_above_or_below_the_block_is_not_in_its_way():
    """Bounding boxes overlap on every two-column page; only a shared band matters."""
    block = _block((44, 300, 553, 420))
    figure = _figure((362, 45, 550, 199))  # ends at y 199, the block starts at 300

    assert not keep_off_figures(block, [figure])
    assert block.bbox.x1 == 553


def test_a_figure_on_the_left_moves_the_text_right():
    block = _block((44, 300, 553, 420))
    figure = _figure((46, 320, 189, 400))

    assert keep_off_figures(block, [figure])

    assert block.bbox.x0 >= 189
    assert block.bbox.x1 == 553


def test_a_figure_covering_most_of_the_box_is_left_to_the_audit():
    """Re-flowing cannot fix a picture that is simply on top of the text."""
    block = _block((44, 100, 553, 200))
    figure = _figure((40, 100, 550, 200))

    assert not keep_off_figures(block, [figure])


def test_a_strip_too_narrow_to_write_in_is_not_taken():
    block = _block((44, 100, 140, 200))
    figure = _figure((60, 100, 120, 200))  # 16pt to the left, 19pt to the right

    assert not keep_off_figures(block, [figure])


def test_two_figures_leaving_a_wide_gap_keep_the_gap():
    block = _block((44, 300, 553, 400))
    left = _figure((46, 320, 150, 380))
    right = _figure((400, 320, 550, 380))

    assert keep_off_figures(block, [left, right])

    assert block.bbox.x0 >= 150 and block.bbox.x1 <= 400


def test_a_wordless_block_is_left_alone():
    block = _block((44, 100, 553, 200), text="   ")
    figure = _figure((300, 100, 550, 200))

    assert not keep_off_figures(block, [figure])


def test_a_page_reports_how_many_boxes_it_moved():
    blocks = [_block((209, 148, 478, 257)), _block((44, 600, 553, 700))]
    figures = [_figure((362, 45, 550, 199))]

    assert keep_page_off_figures(blocks, figures) == 1
    assert blocks[1].bbox.x1 == 553
