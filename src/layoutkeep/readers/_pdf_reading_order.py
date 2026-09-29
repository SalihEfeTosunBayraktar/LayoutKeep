"""Reading order of a page's blocks, columns included.

Sayfadaki blokların okuma sırasını (sütunlar dahil) belirler.
"""

from __future__ import annotations

from layoutkeep.core.docir import (
    Block,
    BlockRole,
)
from layoutkeep.readers._pdf_common import _FULL_WIDTH_RATIO, _MARGIN_RATIO, _TERMINAL_PUNCTUATION

# --------------------------------------------------------------------------------------
# Reading order across multi-column layouts
# --------------------------------------------------------------------------------------


def _reading_order(blocks: list[Block], page_width: float, page_height: float) -> list[int]:
    """Return, for each block (same order as input), its position in reading order.

    Margin blocks (running headers/footers, page numbers) are read first/last regardless of
    their width - a narrow, centred page number must not be treated as a column and sorted
    between two real body columns. Within the remaining body area, full-width blocks (section
    titles) act as horizontal separators; between two separators, column blocks are read
    column-major: all of the left column top-to-bottom, then the next column, never interleaved
    sentence by sentence.
    """
    if not blocks:
        return []
    top_edge = page_height * _MARGIN_RATIO
    bottom_edge = page_height * (1 - _MARGIN_RATIO)
    top_margin = sorted((b for b in blocks if b.bbox.y0 <= top_edge), key=lambda b: b.bbox.y0)
    margin_ids = {id(b) for b in top_margin}
    bottom_margin = sorted(
        (b for b in blocks if id(b) not in margin_ids and b.bbox.y1 >= bottom_edge),
        key=lambda b: b.bbox.y0,
    )
    margin_ids |= {id(b) for b in bottom_margin}
    body = [b for b in blocks if id(b) not in margin_ids]

    full = sorted(
        (b for b in body if b.bbox.width >= _FULL_WIDTH_RATIO * page_width),
        key=lambda b: b.bbox.y0,
    )
    columns = [b for b in body if b.bbox.width < _FULL_WIDTH_RATIO * page_width]
    bands = _cluster_columns(columns)
    use_bands = _looks_like_columns(bands)
    band_of: dict[int, int] = {}
    for band_index, band in enumerate(bands):
        for b in band:
            band_of[id(b)] = band_index

    boundaries = [b.bbox.y0 for b in full]

    def bucket(y0: float) -> int:
        return sum(1 for boundary in boundaries if boundary <= y0)

    buckets: dict[int, list[Block]] = {}
    for b in columns:
        buckets.setdefault(bucket(b.bbox.y0), []).append(b)
    for group in buckets.values():
        if use_bands:
            group.sort(key=lambda b: (band_of[id(b)], b.bbox.y0))
        else:
            # The bands do not look like real columns (see `_looks_like_columns`) - a scattered
            # layout has no single correct reading order, so fall back to plain top-to-bottom,
            # left-to-right instead of pretending the bands are columns to read one at a time.
            group.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))

    body_sequence: list[Block] = []
    for i in range(len(full) + 1):
        body_sequence.extend(buckets.get(i, []))
        if i < len(full):
            body_sequence.append(full[i])

    sequence = top_margin + body_sequence + bottom_margin
    position = {id(b): i for i, b in enumerate(sequence)}
    return [position[id(b)] for b in blocks]


def _cluster_columns(blocks: list[Block]) -> list[list[Block]]:
    """Greedily group blocks with overlapping x-ranges into left-to-right column bands."""
    if not blocks:
        return []
    bands: list[dict] = []
    for b in sorted(blocks, key=lambda b: b.bbox.x0):
        placed = False
        for band in bands:
            if b.bbox.x0 < band["x1"] and b.bbox.x1 > band["x0"]:
                band["x0"] = min(band["x0"], b.bbox.x0)
                band["x1"] = max(band["x1"], b.bbox.x1)
                band["blocks"].append(b)
                placed = True
                break
        if not placed:
            bands.append({"x0": b.bbox.x0, "x1": b.bbox.x1, "blocks": [b]})
    bands.sort(key=lambda band: band["x0"])
    for band in bands:
        band["blocks"].sort(key=lambda b: b.bbox.y0)
    return [band["blocks"] for band in bands]


#: At least this fraction of a band's blocks must have a same-height neighbour in another band
#: for the two to count as genuinely side by side, rather than an accidental x-split.
_COLUMN_MATCH_RATIO = 0.5


def _y_overlaps(a: Block, b: Block) -> bool:
    return a.bbox.y0 < b.bbox.y1 and a.bbox.y1 > b.bbox.y0


def _looks_like_columns(bands: list[list[Block]]) -> bool:
    """True when `_cluster_columns`' bands look like real side-by-side columns.

    A real multi-column layout has columns that coexist: a block in the left column sits next to
    a block in the right column at roughly the same height, because the reader's eye goes down
    one column and back up to the top of the next. A page with no real columns - text scattered
    at arbitrary positions - still gets split into x-bands by `_cluster_columns` whenever two
    unrelated blocks happen to share an x-range, but none of their individual blocks actually
    line up with a block in another band. Checking block-to-block overlap rather than each band's
    overall bounding y-range matters: one scattered band can itself chain several blocks that are
    far apart vertically (each only overlapping the next in x), which would otherwise stretch its
    bounding range across most of the page and make every other band look aligned with it.
    """
    if len(bands) < 2:
        return True
    for i in range(len(bands)):
        for j in range(i + 1, len(bands)):
            a, b = bands[i], bands[j]
            smaller, other = (a, b) if len(a) <= len(b) else (b, a)
            matches = sum(1 for blk in smaller if any(_y_overlaps(blk, o) for o in other))
            if matches / len(smaller) >= _COLUMN_MATCH_RATIO:
                return True
    return False


def _looks_cut_off(block: Block, bottom_edge: float) -> bool:
    if block.role != BlockRole.BODY:
        return False
    if block.bbox.y1 < bottom_edge:
        return False
    text = block.text.rstrip()
    return bool(text) and text[-1] not in _TERMINAL_PUNCTUATION
