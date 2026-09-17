"""How much of the writer's slack below a block the page actually has free.

The writer lays a block's text out in its box plus a slack to the right and below (see
`pdf_writer._layout_rect`): the renderer keeps an inset of its own, and without the slack a short
label is shrunk to fit a box its glyphs already fill. Below a block, though, the slack is taken from
whatever is there - and paragraphs set close together have nothing there. On 46 of The Time
Machine's 120 pages the last line of a paragraph was drawn over the first line of the next (one box
ended at 194.8 pt, the next began at 194.1 pt).

Measured in one place, used by the fitting pass (what fits) and by the writer (what is drawn), so
both agree on the room.
"""

from __future__ import annotations

from layoutkeep.core.docir import Block


def room_below(block: Block, page_blocks: list[Block], slack: float) -> float:
    """The slack below `block` that does not reach a block under it in the same column.

    Negative when the next block starts inside this one - the model's regions can overlap partly
    (5-10 pt on Popular Science), and blocks drawn into each other's boxes were drawn over each
    other. The drawing then stops where the next block starts.
    """
    box = block.bbox
    room = slack
    for other in page_blocks:
        if other is block:
            continue
        o = other.bbox
        # Same column: overlaps horizontally. Beneath: starts below this block's top.
        if min(box.x1, o.x1) - max(box.x0, o.x0) <= 0 or o.y0 <= box.y0:
            continue
        room = min(room, o.y0 - box.y1)
    return room
