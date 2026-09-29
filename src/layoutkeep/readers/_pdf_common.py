"""Raw block/page types, shared thresholds and small geometry used across the PDF reader.

PDF okuyucunun modüllerinin paylaştığı ham blok/sayfa tipleri, eşikler ve küçük geometri yardımcıları.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from layoutkeep.core.docir import (
    BBox,
    Block,
    Page,
)

#: A block at least this wide relative to the page is treated as spanning all columns
#: (running headers/footers, titles) rather than belonging to one column.
_FULL_WIDTH_RATIO = 0.7
#: Top/bottom fraction of the page height considered header/footer territory.
_MARGIN_RATIO = 0.12
#: A short, mostly-digit block in the margin: "3", "- 3 -", "Page 3", "3/10".
_PAGE_NUMBER_RE = re.compile(r"^[\s\-–—.:|/\[\]()]*\d{1,4}[\s\-–—.:|/\[\]()]*$")
_TERMINAL_PUNCTUATION = ".!?…\"')"
#: A body block whose font is at least this much larger than the document's body size reads as
#: a heading rather than a paragraph.
_HEADING_SIZE_RATIO = 1.15
#: Two lines/blocks within this many degrees of each other count as "the same angle" for merging
#: and role logic - pymupdf's `dir` vector carries floating-point noise even for text drawn dead
#: straight.
_ROTATION_MERGE_EPS_KEY = "merge.rotation_eps_deg"  # tunables key; the value is read where it is used
#: Caption text sits within this many points below an image and must not be much larger than it.
_CAPTION_GAP = 24.0


@dataclass(slots=True)
class _RawBlock:
    """A page's text block before reading order and role are decided."""

    block: Block
    top_margin: bool
    bottom_margin: bool


@dataclass(slots=True)
class _RawPage:
    page: Page
    blocks: list[_RawBlock] = field(default_factory=list)
    images: list[BBox] = field(default_factory=list)


def _overlap_share(a: BBox, b: BBox) -> float:
    """How much of `a` lies inside `b`."""
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    area = max(1e-6, (a.x1 - a.x0) * (a.y1 - a.y0))
    return max(0.0, w) * max(0.0, h) / area
