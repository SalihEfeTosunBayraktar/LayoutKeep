"""Mirrored (flipped) text and the boxes it covers.

Ayna görüntüsü (ters çevrilmiş) metni ve kapladığı kutuları bulur.
"""

from __future__ import annotations

import math

from layoutkeep.core.docir import (
    BBox,
)

#: A glyph's offset from its own baseline origin, projected onto where "up" should be. Well
#: clear of zero for real text and safely below the ~0.65 the measurement produces, so it only
#: rejects degenerate glyphs - a space, or a char whose bbox collapsed.
_MIRROR_MIN_PROJECTION = 0.15

#: How much of a text span must sit inside a block's bbox before the span's mirroring is taken
#: to be the block's. Spans come from a different pymupdf call than blocks do, so they are
#: matched by geometry rather than by identity.
_MIRROR_OVERLAP = 0.5


def _span_is_mirrored(span: dict) -> bool:
    """True when this span's text transform has a negative determinant - the text is mirrored.

    `dir` is a flow-direction vector and cannot show this: a line mirrored horizontally and a
    line rotated 180 degrees report exactly the same `dir`. The glyphs still differ, though.
    Under any pure rotation a glyph extends from its baseline origin towards `dir` turned a
    quarter-turn; mirroring flips that side while leaving `dir` untouched. So the sign of the
    projection separates the two, at every angle.

    Measured across rotations of 0, 45, 90, 180 and 270 degrees with and without a mirror: the
    projection is +0.65 for all ten upright cases and -0.65 for all ten mirrored ones. The sign
    is what matters, not the magnitude, so there is no threshold to tune.
    """
    chars = span.get("chars") or []
    dx, dy = span.get("dir", (1.0, 0.0))
    up_x, up_y = dy, -dx
    votes = 0
    for char in chars[:12]:
        origin, bbox = char[2], char[3]
        offset_x = (bbox[0] + bbox[2]) / 2 - origin[0]
        offset_y = (bbox[1] + bbox[3]) / 2 - origin[1]
        length = math.hypot(offset_x, offset_y)
        if length < 1e-9:
            continue
        projection = (up_x * offset_x + up_y * offset_y) / length
        if abs(projection) < _MIRROR_MIN_PROJECTION:
            continue
        votes += 1 if projection < 0 else -1
    return votes > 0


def _mirrored_boxes(page) -> list[tuple[float, float, float, float]]:
    return [s["bbox"] for s in page.get_texttrace() if _span_is_mirrored(s)]


def _covered_by(box: tuple[float, float, float, float], bbox: BBox) -> bool:
    """Whether most of `box` lies inside `bbox`."""
    x0, y0, x1, y1 = box
    width = min(x1, bbox.x1) - max(x0, bbox.x0)
    height = min(y1, bbox.y1) - max(y0, bbox.y0)
    if width <= 0 or height <= 0:
        return False
    area = (x1 - x0) * (y1 - y0)
    return area > 0 and (width * height) / area >= _MIRROR_OVERLAP
