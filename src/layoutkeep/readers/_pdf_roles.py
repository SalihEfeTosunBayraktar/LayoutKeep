"""Block roles: heading, header/footer, page number, caption.

Blok rolleri: başlık, üst/alt bilgi, sayfa numarası, altyazı.
"""

from __future__ import annotations

import re
import statistics

from layoutkeep.core.docir import (
    BBox,
    BlockRole,
)
from layoutkeep.readers._pdf_common import (
    _CAPTION_GAP,
    _HEADING_SIZE_RATIO,
    _MARGIN_RATIO,
    _PAGE_NUMBER_RE,
    _RawBlock,
    _RawPage,
)
from layoutkeep.readers._pdf_reading_order import _looks_cut_off

# --------------------------------------------------------------------------------------
# Role classification
# --------------------------------------------------------------------------------------


def _normalize_for_repetition(text: str) -> str:
    """Fold out page numbers so "Chapter 1 - 3" and "Chapter 1 - 4" compare equal."""
    return re.sub(r"\d+", "#", text.strip().lower())


def _classify_roles(raw_pages: list[_RawPage]) -> None:
    all_blocks = [rb.block for rp in raw_pages for rb in rp.blocks]
    body_sizes: list[tuple[float, int]] = []
    for b in all_blocks:
        for line in b.lines:
            for span in line.spans:
                body_sizes.append((span.style.size, len(span.text)))
    median_size = _weighted_median(body_sizes) if body_sizes else 0.0

    # First pass: page numbers (position + shape, no cross-page evidence needed).
    header_texts: dict[str, int] = {}
    footer_texts: dict[str, int] = {}
    for rp in raw_pages:
        for rb in rp.blocks:
            text = rb.block.text.strip()
            if not text or not (rb.top_margin or rb.bottom_margin):
                continue
            if _PAGE_NUMBER_RE.match(text):
                rb.block.role = BlockRole.PAGE_NUMBER
                continue
            key = _normalize_for_repetition(text)
            if rb.top_margin:
                header_texts[key] = header_texts.get(key, 0) + 1
            else:
                footer_texts[key] = footer_texts.get(key, 0) + 1

    single_page = len(raw_pages) == 1
    # On a single page there is no repetition to confirm a header/footer, so position is all we
    # have - but position alone is only trustworthy when it is unambiguous: a genuine header is
    # the one line sitting alone in the top margin. When several unrelated blocks land in the
    # margin band (a scattered layout, not a real page margin), none of them gets promoted; they
    # stay BODY and get translated, which is the safer default when the page's structure is
    # itself in doubt.
    def _is_short_margin_body(rb: _RawBlock, top: bool) -> bool:
        text = rb.block.text.strip()
        margin = rb.top_margin if top else rb.bottom_margin
        return rb.block.role == BlockRole.BODY and margin and bool(text) and len(text) <= 80

    top_candidates = (
        sum(1 for rb in raw_pages[0].blocks if _is_short_margin_body(rb, top=True))
        if single_page
        else 0
    )
    bottom_candidates = (
        sum(1 for rb in raw_pages[0].blocks if _is_short_margin_body(rb, top=False))
        if single_page
        else 0
    )

    # Second pass: repeating (or, on a single-page doc with one unambiguous candidate,
    # position-only) headers/footers.
    for rp in raw_pages:
        for rb in rp.blocks:
            if rb.block.role != BlockRole.BODY:
                continue
            text = rb.block.text.strip()
            if not text or not (rb.top_margin or rb.bottom_margin):
                continue
            key = _normalize_for_repetition(text)
            if rb.top_margin:
                repeated = header_texts.get(key, 0) >= 2
                if repeated or (single_page and top_candidates == 1 and len(text) <= 80):
                    rb.block.role = BlockRole.HEADER
            else:
                repeated = footer_texts.get(key, 0) >= 2
                if repeated or (single_page and bottom_candidates == 1 and len(text) <= 80):
                    rb.block.role = BlockRole.FOOTER

    # Third pass: headings/title and figure captions, on whatever is still plain body text.
    title_assigned = False
    for rp in raw_pages:
        for rb in rp.blocks:
            block = rb.block
            if block.role != BlockRole.BODY:
                continue
            dominant = block.dominant_style()
            if median_size and dominant.size >= median_size * _HEADING_SIZE_RATIO:
                if not title_assigned:
                    block.role = BlockRole.TITLE
                    title_assigned = True
                else:
                    block.role = BlockRole.HEADING
                continue
            if _near_image(block.bbox, rp.images):
                block.role = BlockRole.CAPTION

    # Fourth pass: flag the last body paragraph on a page as cut off if it runs into the bottom
    # margin without ending in terminal punctuation - it continues onto the next page/column.
    for rp in raw_pages:
        bottom_edge = rp.page.height * (1 - _MARGIN_RATIO)
        body = [rb.block for rb in rp.blocks if rb.block.role == BlockRole.BODY]
        if not body:
            continue
        last = max(body, key=lambda b: b.order)
        if _looks_cut_off(last, bottom_edge):
            last.continues = True


def _weighted_median(sizes: list[tuple[float, int]]) -> float:
    expanded: list[float] = []
    for size, weight in sizes:
        expanded.extend([size] * max(weight, 1))
    return statistics.median(expanded)


def _near_image(bbox: BBox, images: list[BBox]) -> bool:
    """True when `bbox` reads as a caption for one of `images`: directly below it, not much
    wider than it (a full-width body paragraph merely near a small illustration is not a caption)."""
    for img in images:
        overlaps_x = bbox.x0 < img.x1 and bbox.x1 > img.x0
        gap_below = bbox.y0 - img.y1
        narrow_enough = bbox.width <= img.width * 2.5
        if overlaps_x and narrow_enough and 0 <= gap_below <= _CAPTION_GAP:
            return True
    return False
