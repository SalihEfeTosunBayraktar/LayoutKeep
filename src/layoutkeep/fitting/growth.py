"""A block may grow into the space the page really has below it, instead of only its own slack.

WHY THIS EXISTS. `fitting.room.room_below` answers "how much of the writer's 3 pt slack does the
page have free" and never returns more than that slack, so a translation that needs a second line
is shrunk to the floor or flagged as an overflow while the page holds twenty points of blank paper
under the block. Measured on the first real run after the campaign (arXiv 2507.03009 with
gemma-4-e4b): `fitting 70 blocks: shrunk=42 overflow=28` on one table page and `3 blocks:
overflow=3` on an author-list page, and on the NASA scan's first page four of the six overflowing
blocks had 31-39 pt of empty paper beneath them.

WHAT IT GRANTS. The gap to the next block in the same column, less a small remainder, capped by a
tunable and stopped by anything drawn below (a picture, a vector drawing). Nothing is granted when
the gap is already tight: overlapping OCR boxes have negative gaps and get nothing.

The reader already does this for scans, from the pixels (`image_reader._grant_blank_paper`, bounded
by ink). This is the same idea for a page whose text layer says where the text is, bounded by the
blocks and the pictures. One function, used by the fitting pass (what fits) and by the writer (what
is drawn), so the two cannot disagree - which is why `fitting/room.py` exists at all.
"""

from __future__ import annotations

from collections.abc import Sequence

from layoutkeep.core import tunables
from layoutkeep.core.docir import BBox, Block

#: How much of the gap to the next block is left alone, in points. Two paragraphs set one above the
#: other keep a sliver of separation even when the upper one's translation needs the space.
KEEP_PT = 2.0

#: The tunable that caps the grant: how far a block may grow into free space, in points.
GRANT_KEY = "write.grant_room_pt"

#: Roles whose box is a single line by design: a running header, a page number, a title. A
#: translation of one of those that needs a second line is better shrunk (and flagged) than wrapped
#: - wrapping a header changes the shape of the page, which is what the reader was told not to do.
#: Held-out: a running header's translation wrapped onto two lines the moment the grant reached it,
#: and `test_page_number_and_header_survive_untouched` caught it at the full suite.
SINGLE_LINE_ROLES = frozenset({"heading", "title", "header", "footer", "page_number"})


def may_grow(block: Block) -> bool:
    """Whether this block may take the room below it. False for the single-line design elements."""
    return block.role.value not in SINGLE_LINE_ROLES


def free_below(
    block: Block,
    page_blocks: Sequence[Block],
    *,
    limit: float | None = None,
    keep: float = KEEP_PT,
    obstacles: Sequence[BBox | Block] = (),
) -> float:
    """How far `block` may grow downward, in points, into space the page has free.

    Bounded by the next block in the same column, by any obstacle (a picture, a drawing) whose top
    is below this block, and by `limit` - the tunable's value when none is given. `keep` points of
    the original gap stay untouched.
    """
    if limit is None:
        limit = float(tunables.get(GRANT_KEY))
    box = block.bbox
    gap = limit
    for neighbour in [*page_blocks, *obstacles]:
        if neighbour is block:
            continue
        o = getattr(neighbour, "bbox", neighbour)
        if min(box.x1, o.x1) - max(box.x0, o.x0) <= 0:
            continue  # another column: it neither hosts nor bounds this block's growth
        if o.y0 <= box.y0:
            # A neighbour that starts above this block and reaches below its bottom - the shape of
            # an overlapping OCR box - owns the space: nothing may be granted over its glyphs.
            if o.y1 > box.y1 - 0.5:
                gap = 0.0
            continue
        gap = min(gap, o.y0 - box.y1)
    return max(0.0, min(gap, limit) - keep)
