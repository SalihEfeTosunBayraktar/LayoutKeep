"""Merging wrapped lines into blocks, and keeping side-by-side cells apart.

Sarılmış satırları bloklarda birleştirir, yan yana hücreleri ayrı tutar.
"""

from __future__ import annotations

import math

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Line,
)
from layoutkeep.readers._pdf_common import _ROTATION_MERGE_EPS_KEY
from layoutkeep.readers._pdf_table_grid import _table_grid

#: A vertical gap up to this many times the font size still reads as consecutive lines of the
#: same paragraph rather than the start of a new one.
_LINE_MERGE_GAP_KEY = "merge.line_gap_ratio"  # tunables key; the value is read where it is used

#: Rough line box height as a multiple of point size, used to turn a rotated line's centre
#: back into its glyph edges. Matches what `pdf_writer.py` assumes when it stacks them again.
_LINE_HEIGHT_KEY = "merge.line_height_ratio"  # tunables key; the value is read where it is used


#: Two lines belong to the same cell when their x-ranges overlap by at least this much of the
#: narrower one. Wrapped lines of a paragraph overlap almost completely; cells in a row do not
#: overlap at all.
_CELL_OVERLAP_KEY = "table.cell_overlap_ratio"  # tunables key; the value is read where it is used

def _x_overlap_ratio(a: BBox, b: BBox) -> float:
    """How much two boxes overlap horizontally, as a fraction of the narrower one."""
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    narrower = min(a.width, b.width)
    return overlap / narrower if narrower > 0 else 0.0


def _hyphen_parents(lines: list[Line]) -> dict[int, Line]:
    """For each line that continues the one above it across a line break, that line.

    Keyed by `id(line)` - lines are not hashable and `Line` compares by value, which two blank
    lines of a table would satisfy.

    The test is the one the hyphen join is refused on: the line above ends in a hyphen after a
    letter and this one starts lowercase. Where the join *did* run there is nothing left to pair -
    the fragment already moved up - so this only ever fires on the breaks the join leaves alone,
    a URL or a path whose hyphen is part of the text.
    """
    parents: dict[int, Line] = {}
    ordered = sorted(lines, key=lambda ln: ln.bbox.y0)
    for index, line in enumerate(ordered[1:], start=1):
        above = ordered[index - 1]
        text = above.text
        if len(text) < 2 or text[-1] not in "-­‐‑" or not text[-2].isalpha():
            continue
        if not line.text or not line.text[0].islower():
            continue
        parents[id(line)] = above
    return parents


def _cell_groups(lines: list[Line]) -> list[list[Line]]:
    """Group one block's lines into columns: each group is one cell of the row, or one item.

    Two lines are in the same group when they overlap horizontally (same cell, wrapped onto the
    next row) or when one of them continues the other across a line break - a hyphen at the end of
    one and a lowercase start on the next (`_hyphen_parents`). A continuation may be seen before
    the line it continues, because lines are walked left to right; it then waits for that line and
    joins its group, and no unrelated line joins a group that is waiting.
    """
    parents = _hyphen_parents(lines)
    groups: list[list[Line]] = []
    waiting: dict[int, list[Line]] = {}  # id(line) -> lines that continue it

    def place(line: Line, group: list[Line]) -> None:
        group.append(line)
        for follower in waiting.pop(id(line), ()):
            place(follower, group)

    def placed(line: Line) -> bool:
        return any(other is line for group in groups for other in group)

    for line in sorted(lines, key=lambda ln: ln.bbox.x0):
        if placed(line):
            continue  # came in as a continuation of a line before it
        parent = parents.get(id(line))
        if parent is not None and not any(other is line for group in waiting.values() for other in group):
            waiting.setdefault(id(parent), []).append(line)
            continue  # it joins the line it continues, when that line comes round
        group = None
        for candidate in groups:
            if parent is not None:
                if any(other is parent for other in candidate):
                    group = candidate
                    break
            elif any(
                _x_overlap_ratio(line.bbox, other.bbox) >= tunables.get(_CELL_OVERLAP_KEY)
                for other in candidate
            ):
                group = candidate
                break
        if group is None:
            group = []
            groups.append(group)
        place(line, group)
    groups.extend(waiting.values())  # a line whose continuation never came round
    return groups


def _split_side_by_side_lines(blocks: list[Block]) -> list[Block]:
    """Split a block whose lines sit beside each other into one block per cell.

    MuPDF groups by proximity, so a table's header row - three short lines on one baseline -
    arrives as a single block. Read as a paragraph it becomes "Plate Cycles Deflection", and
    the translation of all three is written into the first cell's box.

    A line that continues the one above it across a line break is not a cell of its own, and is
    not a cell of anything else either: arXiv 2507.03009's footer holds a footnote and a URL set
    around it, and the URL's second row - `reference/chat/create`, whose hyphen the join above
    refused because a URL's hyphen is part of the link - overlaps the footnote's column, so it was
    grouped with the footnote and translated as `1See: reference/chat/create`. A line beginning
    lowercase under a line ending in a hyphen belongs to that line, whatever the columns say.

    Lines are walked left to right, as they always were - a note's marker and the text beside it
    belong together, and reading order split `Note.` off the note body it belongs to. A
    continuation seen before the line it continues waits for it and joins its group when the line
    above comes round; no unrelated line joins a group that is waiting.
    """
    out: list[Block] = []
    for block in blocks:
        if len(block.lines) < 2:
            out.append(block)
            continue

        groups = _cell_groups(block.lines)

        if len(groups) < 2:
            out.append(block)
            continue

        for index, group in enumerate(groups):
            bbox = group[0].bbox
            for line in group[1:]:
                bbox = bbox.union(line.bbox)
            out.append(
                Block(
                    id=f"{block.id}c{index}",
                    role=block.role,
                    bbox=bbox,
                    lines=sorted(group, key=lambda ln: ln.bbox.y0),
                    rotation=block.rotation,
                    align=block.align,
                    confidence=block.confidence,
                    needs_review=block.needs_review,
                    review_reason=block.review_reason,
                )
            )
    return out


def _text_axes(bbox: BBox, rotation: float) -> tuple[float, float]:
    """A box's centre in the frame of text set at `rotation`: along the baseline, then across it.

    A rotated paragraph's lines step perpendicular to their baseline, so in page coordinates
    their axis-aligned boxes overlap each other instead of stacking, and the vertical gap between
    two consecutive lines comes out negative. Measured across the baseline instead, they stack
    exactly the way horizontal lines do. The boxes themselves cannot simply be rotated: the
    axis-aligned box of a 45-degree line is nearly square, and turning a square gives a bigger
    square, not the line back.
    """
    radians = math.radians(rotation)
    cos, sin = math.cos(radians), math.sin(radians)
    cx = (bbox.x0 + bbox.x1) / 2
    cy = (bbox.y0 + bbox.y1) / 2
    return cx * cos + cy * sin, -cx * sin + cy * cos


def _across_span(block: Block, rotation: float) -> tuple[float, float]:
    """Where a rotated block starts and ends across its baseline, padded out to its glyph edges.

    The block's own lines are measured, not the block, so a block that already holds several
    lines is compared from its last line rather than its middle.
    """
    centres = [_text_axes(line.bbox, rotation)[1] for line in block.lines]
    if not centres:
        centres = [_text_axes(block.bbox, rotation)[1]]
    half = block.dominant_style().size * tunables.get(_LINE_HEIGHT_KEY) / 2
    return min(centres) - half, max(centres) + half


def _along_reach(bbox: BBox) -> float:
    """An upper bound on how far a rotated line runs along its own baseline."""
    return math.hypot(bbox.width, bbox.height)


def _merge_wrapped_lines(blocks: list[Block]) -> list[Block]:
    """Merge text blocks that PyMuPDF split apart but that are really one paragraph.

    `get_text("dict")` usually already groups a paragraph's wrapped lines into a single block,
    so that grouping is used as-is elsewhere in this module. But on pages with irregular leading
    - notably a multi-line heading placed with extra line spacing - it can hand back each visual
    line as its own block. Two blocks merge here when they share the same dominant font size,
    sit close enough vertically to read as consecutive lines of one block rather than separate
    ones, and their x-ranges overlap. This runs before reading order and role classification, so
    a merged heading gets one position and one role instead of being scattered and split.
    """
    # Cells that line up into columns across rows are a table. Merging one row into the next
    # turns the whole thing into a single block whose translation is written into the first
    # cell, which is what the README's own comparison image was showing.
    grid_positions = _table_grid(blocks)
    in_grid = set(grid_positions)

    remaining = sorted(blocks, key=lambda b: b.bbox.y0)
    merged: list[Block] = []
    while remaining:
        current = remaining.pop(0)
        if current.id in in_grid:
            table_id, row, col = grid_positions[current.id]
            current.role = BlockRole.TABLE
            current.table_id = table_id
            current.table_row = row
            current.table_col = col
            merged.append(current)
            continue
        while True:
            best_index: int | None = None
            best_gap = 0.0
            size = current.dominant_style().size
            rotated = abs(current.rotation) > tunables.get(_ROTATION_MERGE_EPS_KEY)
            # A tilted paragraph is measured along and across its own baseline, so that "the
            # line below this one" and "sits over the same span" mean what they mean for
            # upright text. Without it a rotated heading is never merged and each of its visual
            # lines is translated alone, out of the sentence it belongs to.
            if rotated:
                here_along, _ = _text_axes(current.bbox, current.rotation)
                _, here_end = _across_span(current, current.rotation)
            for i, candidate in enumerate(remaining):
                if abs(candidate.rotation - current.rotation) > tunables.get(_ROTATION_MERGE_EPS_KEY):
                    continue  # different angle - not the same paragraph however close it sits
                if rotated:
                    there_along, _ = _text_axes(candidate.bbox, current.rotation)
                    there_start, _ = _across_span(candidate, current.rotation)
                    gap = there_start - here_end
                    reach = max(_along_reach(current.bbox), _along_reach(candidate.bbox))
                    overlaps = abs(there_along - here_along) < reach / 2
                else:
                    gap = candidate.bbox.y0 - current.bbox.y1
                    overlaps = not (
                        current.bbox.x0 >= candidate.bbox.x1
                        or current.bbox.x1 <= candidate.bbox.x0
                    )
                if gap < 0 or size <= 0 or candidate.dominant_style().size != size:
                    continue
                if gap > size * tunables.get(_LINE_MERGE_GAP_KEY):
                    continue
                if candidate.id in in_grid:
                    continue  # a table cell, not the next line of this paragraph
                if not overlaps:
                    continue  # not stacked over the same span of the line above
                if best_index is None or gap < best_gap:
                    best_index, best_gap = i, gap
            if best_index is None:
                break
            candidate = remaining.pop(best_index)
            current = Block(
                id=current.id,
                role=current.role,
                bbox=current.bbox.union(candidate.bbox),
                lines=current.lines + candidate.lines,
                confidence=min(current.confidence, candidate.confidence),
                needs_review=current.needs_review or candidate.needs_review,
                rotation=current.rotation,
                # Two lines that are each centred make a centred block. Leaving this out reset
                # every merged block to "left" - a cover title of two centred lines was drawn
                # flush left.
                align=current.align if current.align == candidate.align else "left",
            )
        merged.append(current)
    return merged
