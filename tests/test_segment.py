"""XY-cut segmentation, against every layout that defeated the per-line rules.

The cases here are not invented. Each is one that a per-line rule got right while breaking
another, which is why the decision moved to the page's whitespace instead:

    single column           three rules got this right, one broke it
    two columns             the case six page styles exposed
    columns under a title   broke the "cluster by overlap" rule
    body with margin notes  the case the "body column" rule exists for
    prose above a figure    broke the "cluster narrow lines first" rule

The last one is the reason this approach is different in kind rather than better tuned: the
figure is separated from the prose by a horizontal gap, so the first cut isolates it and its
scattered labels are only ever compared with each other. The prose is never examined against
them at all.
"""

from __future__ import annotations

from layoutkeep.ocr.engine import TextBox
from layoutkeep.readers._segment import segment

_H = 8.0
_PITCH = 12.0


def _line(x0: float, top: float, width: float, text: str = "x") -> list[TextBox]:
    return [TextBox(text=text, bbox=(x0, top, x0 + width, top + _H), confidence=0.99)]


def _shape(regions) -> list[int]:
    return [len(r.lines) for r in regions]


def _column(x0: float, rows: int, *, top: float = 70.0, width: float = 210.0):
    return [_line(x0, top + row * _PITCH, width) for row in range(rows)]


def test_a_single_column_stays_one_region() -> None:
    """Paragraph leading must not read as structure - it is under one line height."""
    assert _shape(segment(_column(74.0, 5, width=230.0))) == [5]


def test_two_columns_are_two_regions() -> None:
    """The gutter is a tall empty vertical band, and wider than any gap inside a column."""
    lines = []
    for row in range(5):
        lines.append(_line(60.0, 70.0 + row * _PITCH, 210.0))
        lines.append(_line(310.0, 70.0 + row * _PITCH, 210.0))
    assert sorted(_shape(segment(lines))) == [5, 5]


def test_each_region_holds_one_column_only() -> None:
    """The count alone would not prove it: check no region straddles the gutter."""
    lines = []
    for row in range(4):
        lines.append(_line(60.0, 70.0 + row * _PITCH, 210.0))
        lines.append(_line(310.0, 70.0 + row * _PITCH, 210.0))
    for region in segment(lines):
        lefts = {min(b.bbox[0] for b in line) for line in region.lines}
        assert len(lefts) == 1, f"a region spans two columns: {sorted(lefts)}"


def test_a_title_above_two_columns_is_its_own_region() -> None:
    """The horizontal gap under the title is cut before the gutter, so the title never joins a
    column and never welds the two together."""
    title = _line(60.0, 30.0, 460.0, text="A Heading Across The Page")
    lines = [title]
    for row in range(4):
        lines.append(_line(60.0, 90.0 + row * _PITCH, 210.0))
        lines.append(_line(310.0, 90.0 + row * _PITCH, 210.0))
    assert sorted(_shape(segment(lines))) == [1, 4, 4]


def test_margin_notes_separate_from_the_body() -> None:
    """A keyword in the left margin sits across a wide empty vertical band from the prose."""
    lines = _column(74.0, 5, width=230.0)
    lines.append(_line(10.0, 82.0, 20.0, text="OR"))
    lines.append(_line(10.0, 118.0, 26.0, text="NAND"))
    regions = segment(lines)
    assert sorted(_shape(regions)) == [2, 5], _shape(regions)


def test_prose_above_a_figure_is_not_split_by_its_labels() -> None:
    """The case three per-line rules broke.

    Scattered short labels below a paragraph used to drag the "body column" across the page, and
    every line of the paragraph was then taken for a margin note. Here the figure is cut off
    first, so the paragraph is never compared with the labels.
    """
    lines = _column(74.0, 5, width=230.0)
    for x0 in (150.0, 200.0, 260.0, 240.0, 280.0):
        lines.append(_line(x0, 200.0, 20.0, text="D0"))
    regions = segment(lines)
    prose = [r for r in regions if len(r.lines) == 5]
    assert prose, f"the five-line paragraph did not survive: {_shape(regions)}"
    assert {min(b.bbox[0] for b in line) for line in prose[0].lines} == {74.0}


def test_no_lines_is_no_regions() -> None:
    assert segment([]) == []


def test_reading_order_is_top_then_left() -> None:
    regions = segment(
        [
            _line(60.0, 30.0, 460.0, text="title"),
            *_column(60.0, 4, top=90.0),
            *_column(310.0, 4, top=90.0),
        ]
    )
    firsts = [region.lines[0][0].text for region in regions]
    assert firsts[0] == "title", firsts
