"""Regrouping a digital page's text by the layout model's regions.

Dijital sayfanın metnini düzen modelinin bölgelerine göre yeniden gruplar; bölgeyi boşluklardan
ve yan yana satırlardan ayırır.
"""

from __future__ import annotations

import itertools
import statistics

import pymupdf
from PIL import Image

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Line,
)
from layoutkeep.ocr.engine import TextBox
from layoutkeep.ocr.layout_detector import LABEL_TO_ROLE, LayoutDetector, resolve_duplicates
from layoutkeep.readers._layout import infer_alignment
from layoutkeep.readers._pdf_raster_labels import _raster_labels
from layoutkeep.readers._pdf_table_cells import _horizontal_rules, _label_role, _table_cells
from layoutkeep.readers._segment import segment

#: Resolution a born-digital page is rendered at for the layout model. The model resizes to 640px
#: whatever it is given, so this only needs to keep small type legible to it.
_DIGITAL_LAYOUT_DPI = 100

#: Regions whose lines are separate items, not a paragraph: a table of contents is one entry per
#: line, a table one cell per line, a figure one label per line.
_ONE_BLOCK_PER_LINE = frozenset({"document_index", "table", "form", "key_value_region", "picture"})

#: How much of a line has to lie inside a region to belong to it.
_DIGITAL_REGION_MEMBERSHIP = 0.5


def _regroup_by_layout(
    page: pymupdf.Page, index: int, blocks: list[Block], layout: LayoutDetector
) -> tuple[list[Block], list[Block]]:
    """Group a born-digital page's lines by the layout model's regions.

    Regions come from the model, looking at the rendered page; text, fonts and positions still
    come from the PDF, so nothing is re-recognised. Returns (blocks the model did not claim, for
    the existing rules; blocks built from the model's regions).

    Campaign, NIST SP 800-12 page 6: a table of contents came out with its entries run together,
    because the rules merged its lines into paragraphs. The model labels that page
    `document_index`, and each of its lines is one entry.

    Rotated text is left to the rules: its line boxes are not what the model sees upright.
    """
    pixmap = page.get_pixmap(dpi=_DIGITAL_LAYOUT_DPI)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    sx, sy = page.rect.width / pixmap.width, page.rect.height / pixmap.height
    regions = [
        (r.label, BBox(r.bbox[0] * sx, r.bbox[1] * sy, r.bbox[2] * sx, r.bbox[3] * sy))
        for r in resolve_duplicates(layout.detect(image))
    ]
    if not regions:
        return blocks, []

    unclaimed: list[Block] = []
    members: dict[int, list[Line]] = {}
    for block in blocks:
        if abs(block.rotation) > 1e-3:
            unclaimed.append(block)
            continue
        # The unclaimed lines, in runs of consecutive ones: a claimed line ends the run above it.
        # Leftovers are one paragraph only where nothing else sits between them - the box is what
        # the writer draws the translation into. Turkish Penal Code page 2 (a Word-generated PDF)
        # arrived as ONE pymupdf block of 43 lines holding the whole page, and the union box of its
        # leftovers was y 83..418, 335 pt tall: 'Madde 175', a heading at y 130 and '(2) Kara...'
        # at y 324-346 in one block, drawn as a strip at the top of the page while the places those
        # lines came from were left blank.
        runs: list[list[Line]] = []
        current: list[Line] | None = None
        for line in block.lines:
            owner = _owning_region(line.bbox, regions) if line.bbox is not None else None
            if owner is not None:
                members.setdefault(owner, []).append(line)
                current = None
                continue
            # A line of spaces is no part of a paragraph: on the Turkish Penal Code one sat on a
            # heading's row, joined the article's run and stretched its box over the heading (L7).
            if not "".join(span.text for span in line.spans).strip():
                continue
            if current is None:
                current = []
                runs.append(current)
            current.append(line)
        for position, run in enumerate(runs):
            box = run[0].bbox
            for line in run[1:]:
                if line.bbox is not None:
                    box = line.bbox if box is None else box.union(line.bbox)
            unclaimed.append(
                Block(
                    # The first run keeps the block's own id - it is that block as the reading
                    # order, the table grid and the review flags knew it; the later ones are
                    # numbered off it, the way the region-built blocks are (`#m…`).
                    id=block.id if position == 0 else f"{block.id}.{position}",
                    role=block.role, bbox=box or block.bbox, lines=run,
                    rotation=block.rotation, align=block.align,
                    needs_review=block.needs_review, review_reason=block.review_reason,
                )
            )

    width = page.rect.width
    heights = [
        line.bbox.y1 - line.bbox.y0 for block in blocks for line in block.lines if line.bbox is not None
    ]
    line_height = statistics.median(heights) if heights else 1.0
    rules: list[pymupdf.Rect] | None = None  # read once, only when the page has a table
    built: list[Block] = []
    for owner, lines in sorted(members.items()):
        label, _box = regions[owner]
        lines.sort(key=lambda line: (line.bbox.y0, line.bbox.x0))
        if label == "table":
            if rules is None:
                rules = _horizontal_rules(page)
            groups = _table_cells(lines, rules, line_height)
        elif label in _ONE_BLOCK_PER_LINE:
            groups = [[line] for line in lines]
        else:
            # A region can hold more than one column - a references page's "[SP800-57 part 1]" label
            # beside its entry came as one region, and sorted by height the label was interleaved
            # into the entry. The page's whitespace separates them, as it does on scanned pages.
            groups = _cut_by_whitespace(lines, line_height)
        if label == "picture":
            # A picture's text is part of the picture and stays as it is, as on scanned pages: a
            # stack diagram's labels translated line by line renamed its variables ("letters" ->
            # "harfler"), changed a value ('c' -> 'k') and lost "__main__" (Think Python p. 97).
            role = BlockRole.FIGURE
        elif label == "table":
            role = BlockRole.TABLE
        elif label in _ONE_BLOCK_PER_LINE:
            role = BlockRole.BODY
        else:
            role = LABEL_TO_ROLE.get(label, BlockRole.BODY)
        for group in groups:
            box = group[0].bbox
            for line in group[1:]:
                box = box.union(line.bbox)
            built.append(
                Block(
                    id=f"p{index}#m{owner}.{len(built)}", role=_label_role(role, group), bbox=box,
                    lines=group,
                    align=infer_alignment(box, width),
                )
            )
    if tunables.get("translation.figure_text"):
        taken = [b.bbox for b in [*unclaimed, *built]]
        for owner, (label, box) in enumerate(regions):
            if label == "picture":
                built.extend(_raster_labels(page, index, owner, box, taken))
    return unclaimed, built


def _cut_by_whitespace(lines: list[Line], line_height: float) -> list[list[Line]]:
    """Split a region's lines at the page's structural gaps (see `readers/_segment.py`)."""
    stand_ins = [
        [TextBox(text=str(i), bbox=(ln.bbox.x0, ln.bbox.y0, ln.bbox.x1, ln.bbox.y1), confidence=1.0)]
        for i, ln in enumerate(lines)
    ]
    groups = [
        [lines[int(stand_in[0].text)] for stand_in in region.lines]
        for region in segment(stand_ins, line_height=line_height)
    ]
    return [
        paragraph
        for group in groups
        for part in _split_side_by_side_rows(group)
        for paragraph in _split_at_blank_lines(part, line_height)
    ]


#: A gap between two stacked lines of one region at least this many times the region's usual gap
#: between lines is a blank line between paragraphs.
_PARAGRAPH_GAP_FACTOR = 3.0


def _split_at_blank_lines(lines: list[Line], line_height: float) -> list[list[Line]]:
    """Split stacked lines where a blank line separates paragraphs.

    Held-out Wikipedia "Printing press", page 9: one text region held the whole page, and its four
    paragraphs, 15 pt apart against 2.5-3 pt between lines, stayed under the whitespace cut's
    threshold of 1.2 line heights (15.9 pt) - one 4,000-character block the model never answered, and
    the page was lost. Measured against the region's own spacing, a blank line is unmistakable; half
    a line height is the least a gap must be, so tight leading does not turn every line into one.
    """
    ordered = sorted(lines, key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
    # Lines set tighter than their boxes overlap a little: that is a gap of nothing, not less.
    gaps = [max(b.bbox.y0 - a.bbox.y1, 0.0) for a, b in itertools.pairwise(ordered)]
    if len(gaps) < 2:
        return [lines]
    threshold = max(_PARAGRAPH_GAP_FACTOR * statistics.median(gaps), 0.5 * line_height)
    parts: list[list[Line]] = [[ordered[0]]]
    for gap, line in zip(gaps, ordered[1:], strict=True):
        if gap >= threshold:
            parts.append([line])
        else:
            parts[-1].append(line)
    return parts


def _split_side_by_side_rows(lines: list[Line]) -> list[list[Line]]:
    """Split a group where two lines sit side by side on one row, at the gap between them.

    Two lines on the same row cannot be one run of text, however narrow the gap: NIST's one-line
    reference labels ("[SP800-39]", x 77-136) sit 18 pt from their entries (x 154) - just under the
    whitespace threshold for 16 pt lines - and were read into the middle of the entry.
    """
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            overlap = min(a.bbox.y1, b.bbox.y1) - max(a.bbox.y0, b.bbox.y0)
            shorter = min(a.bbox.y1 - a.bbox.y0, b.bbox.y1 - b.bbox.y0)
            if shorter <= 0 or overlap < shorter * 0.5:
                continue
            # A footnote mark set as its own tiny line beside a word is not a column.
            if min(a.bbox.x1 - a.bbox.x0, b.bbox.x1 - b.bbox.x0) < 2 * shorter:
                continue
            left, right = (a, b) if a.bbox.x1 <= b.bbox.x0 else (b, a) if b.bbox.x1 <= a.bbox.x0 else (None, None)
            if left is None:
                continue
            cut = (left.bbox.x1 + right.bbox.x0) / 2
            # Think Python p. 139: a justified line came out as two lines around a stretched space.
            # A paragraph's other lines run across that gap; two side-by-side columns leave it empty.
            if any(ln.bbox.x0 < cut < ln.bbox.x1 for ln in lines):
                continue
            before =sorted((ln for ln in lines if ln.bbox.x1 <= cut), key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
            after = sorted((ln for ln in lines if ln.bbox.x1 > cut), key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
            if before and after:
                return _split_side_by_side_rows(before) + _split_side_by_side_rows(after)
    return [lines]


def _owning_region(box: BBox, regions: list[tuple[str, BBox]]) -> int | None:
    """The smallest region holding at least half of `box`."""
    area = max((box.x1 - box.x0) * (box.y1 - box.y0), 1e-6)
    best, best_area = None, float("inf")
    for i, (_label, region) in enumerate(regions):
        ix = max(0.0, min(box.x1, region.x1) - max(box.x0, region.x0))
        iy = max(0.0, min(box.y1, region.y1) - max(box.y0, region.y0))
        size = (region.x1 - region.x0) * (region.y1 - region.y0)
        if ix * iy / area >= _DIGITAL_REGION_MEMBERSHIP and size < best_area:
            best, best_area = i, size
    return best
