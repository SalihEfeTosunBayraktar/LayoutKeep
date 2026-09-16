"""Cut a page into regions by its own whitespace, instead of classifying each line in isolation.

WHY THIS EXISTS. Every defect the scanned path acquired came from the same shape of mistake: a
line was judged against a constant, and the constant was calibrated on one page. Six
deliberately different page styles found the limit of that approach - five read cleanly and a
two-column page came back with eight of sixteen blocks starting mid-sentence, because the "body
column" is a single number and a page with two columns has two. Three different per-line rules
were tried and each broke a case that already worked:

  * "a line spanning most of the page belongs to no column" - a single-column body line spans
    72% of its page legitimately, so every body line became its own column;
  * "cluster lines by horizontal overlap" - a full-width title overlaps both columns and glues
    them back into one;
  * "cluster the narrow lines first" - scattered figure labels are narrow, so they became the
    columns and the real body lines looked like they spanned several.

The fault is not the thresholds. It is that a line cannot be classified without knowing the
page's structure, and the page's structure is in its whitespace.

WHAT THIS DOES. Recursive XY-cut, the classic decomposition: project the lines onto an axis,
find the widest empty band, split there, recurse. A gutter is a tall empty vertical band; a
paragraph break or the space above a figure is a wide empty horizontal one. The same recursion
handles every case that defeated the per-line rules, and handles the hardest one - scattered
figure labels - for a reason worth stating: the figure is separated from the prose by a
horizontal gap, so the first cut isolates the figure band and the labels are only ever compared
with each other. The prose above it is never split at all.

WHAT IS STILL A JUDGEMENT. One number: how empty a band has to be, relative to the page's own
line height, before it counts as a structural gap (`_MIN_GAP_LINES`). It is expressed in line
heights measured off this page, so a 318pt textbook and an A4 notebook run the same code with
different numbers - which is the property the previous constants lacked. Everything else -
where the cuts fall, how many there are, how deep the recursion goes - comes from the page.

This module is geometry only: it knows `TextBox` and nothing about DocIR, OCR or pymupdf.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from itertools import pairwise

from layoutkeep.ocr.engine import TextBox

#: A line, as this module sees it: the boxes that make it up.
Line = list[TextBox]

#: How many line heights of empty space make a structural gap.
#:
#: Below a line height, an empty band is the leading between two lines of one paragraph. Well
#: above it, the band is a gutter, the space above a figure, or the margin beside a note. The
#: threshold is in line heights measured on this page, so it carries no assumption about page
#: size, type size or scan resolution - which is exactly what the constants this replaces did
#: carry.
_MIN_GAP_LINES = 1.2

#: A region is only worth cutting further if it holds more than this many lines. A one- or
#: two-line region is already as small as a region gets, and recursing into it turns a paragraph
#: into its own lines - the failure this whole module exists to avoid.
_MIN_LINES_TO_CUT = 3


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle of the page and the lines inside it, in reading order."""

    lines: list[Line]

    @property
    def x0(self) -> float:
        return min(min(b.bbox[0] for b in line) for line in self.lines)

    @property
    def y0(self) -> float:
        return min(min(b.bbox[1] for b in line) for line in self.lines)


def _line_height(lines: list[Line]) -> float:
    heights = [
        max(b.bbox[3] for b in line) - min(b.bbox[1] for b in line) for line in lines
    ]
    return statistics.median(heights) if heights else 1.0


def _widest_gap(
    intervals: list[tuple[float, float]], minimum: float
) -> tuple[float, float] | None:
    """The widest empty band between a set of intervals, or None if none is wide enough.

    Intervals are the lines' extents on one axis. Overlapping ones are merged first, so a gap is
    genuinely empty across the whole region rather than merely between two particular lines.
    """
    if len(intervals) < 2:
        return None
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    best: tuple[float, float] | None = None
    best_width = minimum
    for (_, end), (start, _) in pairwise(merged):
        width = start - end
        if width > best_width:
            best_width = width
            best = (end, start)
    return best


def segment(lines: list[Line], *, line_height: float | None = None) -> list[Region]:
    """Split a page's lines into regions, in reading order.

    Reading order is the order the cuts produce: a horizontal cut yields top before bottom, a
    vertical cut yields left before right. For the layouts this handles - one or more columns,
    with full-width matter above or below them - that is the order a reader would use.

    `line_height` is measured from `lines` unless given. It is given when the "lines" are really
    whole blocks being put in reading order: a block is several lines tall, and measuring the gap
    threshold off block heights would make every paragraph break too narrow to count.
    """
    if not lines:
        return []
    return _split(lines, line_height if line_height is not None else _line_height(lines))


def _split(lines: list[Line], line_height: float) -> list[Region]:
    if len(lines) < _MIN_LINES_TO_CUT:
        return [Region(lines=_reading_order(lines))]

    minimum = line_height * _MIN_GAP_LINES
    horizontal = _widest_gap(
        [(min(b.bbox[1] for b in line), max(b.bbox[3] for b in line)) for line in lines],
        minimum,
    )
    vertical = _widest_gap(
        [(min(b.bbox[0] for b in line), max(b.bbox[2] for b in line)) for line in lines],
        minimum,
    )

    # The widest gap wins. A page's gutter is usually wider than its paragraph spacing, and its
    # figure separation wider still, so the most significant structure is cut first and the rest
    # is decided inside the pieces where there is less to confuse it.
    h_width = (horizontal[1] - horizontal[0]) if horizontal else 0.0
    v_width = (vertical[1] - vertical[0]) if vertical else 0.0
    if h_width <= 0 and v_width <= 0:
        return [Region(lines=_reading_order(lines))]

    if h_width >= v_width:
        cut = (horizontal[0] + horizontal[1]) / 2.0
        above = [line for line in lines if max(b.bbox[3] for b in line) <= cut]
        below = [line for line in lines if max(b.bbox[3] for b in line) > cut]
        parts = [above, below]
    else:
        cut = (vertical[0] + vertical[1]) / 2.0
        left = [line for line in lines if max(b.bbox[2] for b in line) <= cut]
        right = [line for line in lines if max(b.bbox[2] for b in line) > cut]
        parts = [left, right]

    if not all(parts):
        # The cut separated nothing - stop rather than recurse forever.
        return [Region(lines=_reading_order(lines))]

    regions: list[Region] = []
    for part in parts:
        regions.extend(_split(part, line_height))
    return regions


def _reading_order(lines: list[Line]) -> list[Line]:
    """Top to bottom, then left to right - within a region there is nothing else to go on."""
    return sorted(
        lines, key=lambda line: (min(b.bbox[1] for b in line), min(b.bbox[0] for b in line))
    )
