"""Geometry helpers shared by the readers.

`_infer_alignment` started in `pdf_reader.py` and is pure geometry - no pymupdf, no DocIR
beyond BBox - so both readers can use it. It lives here rather than being imported across,
because `pdf_reader` already imports `image_reader` (to hand it a rasterised page) and reaching
back the other way would close the loop.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox


def infer_alignment(bbox: BBox, page_width: float) -> str:
    """Infer a block's horizontal alignment from its x-position relative to the page.

    A centred block sits roughly symmetric around the page midline; a right-aligned block sits
    close to the right margin while a left-aligned one hugs the left. Thresholds are generous so
    full-width justified paragraphs (which span most of the page) are not misread as centred.
    Only applies to blocks that leave a real margin on at least one side, so a block that already
    fills the page stays "left"/justify rather than being guessed at.
    """
    if page_width <= 0:
        return "left"
    left_margin = bbox.x0
    right_margin = page_width - bbox.x1
    block_center = (bbox.x0 + bbox.x1) / 2.0
    page_center = page_width / 2.0

    # A block that spans nearly the whole page is justified/full-width, not centred.
    span = bbox.x1 - bbox.x0
    if span >= page_width * 0.8:
        return "left"

    # Centred: the block's middle sits near the page's middle, with balanced margins.
    if abs(block_center - page_center) <= page_width * 0.05 and min(left_margin, right_margin) > 0:
        return "center"
    # Right-aligned: hugged to the right edge, with a large left margin and small right one.
    if right_margin <= page_width * 0.05 and left_margin > page_width * 0.15:
        return "right"
    return "left"
