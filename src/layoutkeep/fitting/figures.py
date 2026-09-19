"""Keep re-flowed text off the pictures on a page.

WHY THIS EXISTS: a PDF text block is reported as the *bounding box* of the lines that wrap around a
figure - the lines beside the picture are short, the lines under it are long, and the box is the
union of the two. The translation is then laid out into that box from scratch, so its first lines
run the full width and land on the picture. Measured on a Wikipedia article: 87 words of Turkish
sitting on a photograph of a printing press, with the audit reporting no loss at all, because L7
only ever looked for text over *text*.

The fix is deliberately conservative: the box handed to the layout engine is narrowed to the widest
strip that no figure occupies, whenever a figure shares the block's vertical band. The lines under
the picture lose width they could have used, and the fitting pass pays for it in type size - but a
page whose text sits on a photograph is unreadable, and this cannot produce one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from layoutkeep.core.docir import BBox, Block, ImageRef

#: A strip narrower than this is not worth re-flowing into: the text would be squeezed to a few
#: characters a line, which is worse than leaving the block alone for the audit to flag.
MIN_STRIP_PT = 36.0

#: Never take more than this share of the block's width away. A figure that overlaps most of the
#: box is not something a narrower box can fix.
MAX_TAKEN = 0.75

#: A hairline of clearance, on top of the writer's own slack: a box that ends exactly on the
#: picture's edge still draws a glyph's right side into it.
CLEARANCE_PT = 1.0


@dataclass(frozen=True, slots=True)
class Strip:
    """The horizontal band a block may use, once the figures in its way are taken out."""

    x0: float
    x1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0


def _bands(block: Block, figures: Sequence[ImageRef]) -> list[ImageRef]:
    """The figures that share a vertical band with the block.

    A picture above or below the block is not in its way, however much the bounding boxes overlap
    once the columns are side by side - which is the normal case on a two-column paper.
    """
    return [
        figure
        for figure in figures
        if figure.bbox.y1 > block.bbox.y0 + 0.5 and figure.bbox.y0 < block.bbox.y1 - 0.5
    ]


def _widest_free_strip(block: Block, figures: Sequence[ImageRef], clearance: float) -> Strip | None:
    """The widest strip of the block's box that no figure covers, or None if nothing is worth it."""
    left, right = block.bbox.x0, block.bbox.x1
    blocked = sorted(
        (max(left, figure.bbox.x0), min(right, figure.bbox.x1))
        for figure in figures
        if figure.bbox.x1 > left and figure.bbox.x0 < right
    )
    if not blocked:
        return None
    # Merge the overlapping intervals, then the gaps between them are what the text may use.
    merged: list[list[float]] = [list(blocked[0])]
    for start, end in blocked[1:]:
        if start <= merged[-1][1] + 0.5:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    gaps: list[Strip] = []
    cursor = left
    for start, end in merged:
        if start - cursor > 0:
            gaps.append(Strip(cursor, start - CLEARANCE_PT))
        cursor = max(cursor, end + CLEARANCE_PT)
    if right - cursor > 0:
        gaps.append(Strip(cursor, right))
    if not gaps:
        return None
    best = max(gaps, key=lambda strip: strip.width)
    return Strip(best.x0, best.x1 - clearance)


def keep_off_figures(block: Block, figures: Sequence[ImageRef], *, clearance: float = 0.0) -> bool:
    """Narrow `block.bbox` until no figure shares its vertical band. True when it changed.

    `clearance` is the room the writer will add to the right of the box on its own (the box slack),
    kept out of the strip so the drawn text cannot creep back over the picture.
    """
    if not figures or not block.text.strip():
        return False
    width = block.bbox.width
    strip = _widest_free_strip(block, _bands(block, figures), clearance)
    if strip is None:
        return False
    if width - strip.width > MAX_TAKEN * width:
        return False  # a figure over most of the box is beyond what re-flowing can fix
    if strip.width < MIN_STRIP_PT:
        return False  # a few characters a line is worse than leaving it for the audit to flag
    block.bbox = BBox(
        round(strip.x0, 2), block.bbox.y0, round(strip.x1, 2), block.bbox.y1
    )
    return True


def keep_page_off_figures(blocks: Sequence[Block], figures: Sequence[ImageRef], *, clearance: float = 0.0) -> int:
    """Apply `keep_off_figures` across one page; returns how many blocks were narrowed."""
    return sum(1 for block in blocks if keep_off_figures(block, figures, clearance=clearance))
