"""A page the cheap OCR pass read badly gets one more pass at higher resolution.

200 DPI was chosen from a single page - page 61, where 300 DPI cost twice the pixels and
garbled a line the lower resolution read cleanly. That generalised from one observation, and
page 54 shows the other side of it: the source is a pristine 600-DPI scan of
"1-10. Simplify the following expressions in (1) sum-of-products form", and at 200 DPI it came
out as "1-10.Sin os -ns ( s ms o ong". At 300 DPI the same line reads correctly.

Across six pages the difference is small - +1.5% characters, +0.006 mean confidence - so
raising the resolution everywhere would pay 2.25x the pixels for almost nothing, and OCR is the
CPU-bound half of a run. The cost belongs only where the cheap pass actually failed, and it is
detectable: measured over nine pages, the share of boxes below the review threshold is 0.0-4.7%
on the seven good ones and 12.0% and 11.2% on the two bad ones.

Both passes are kept and the better one wins, rather than the higher resolution simply
replacing the lower. That is what page 61 was telling me: more pixels is not automatically
better, so the reader measures instead of assuming.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Page, Span, Style
from layoutkeep.readers.image_reader import needs_higher_resolution


def _page(*confidences: float) -> Page:
    page = Page(number=1, width=318.0, height=424.0, source_ref="0")
    style = Style()
    page.blocks = [
        Block(
            id=f"b{i}",
            role=BlockRole.BODY,
            bbox=BBox(0, i * 10, 100, i * 10 + 8),
            lines=[Line(spans=[Span(text="x", bbox=BBox(0, 0, 10, 8), style=style)])],
            confidence=c,
        )
        for i, c in enumerate(confidences)
    ]
    return page


def test_a_clean_page_is_not_read_twice() -> None:
    """Seven of the nine measured pages look like this; paying twice for them is the whole cost
    this avoids."""
    assert needs_higher_resolution(_page(*([0.99] * 19), 0.5)) is False


def test_a_page_full_of_doubt_is_read_again() -> None:
    """Page 54's shape: roughly one box in eight below the threshold."""
    assert needs_higher_resolution(_page(*([0.99] * 14), 0.63, 0.61, 0.7, 0.55, 0.6, 0.5)) is True


def test_an_empty_page_is_not_read_again() -> None:
    """A page with no text at all is not a failed read - it is a plate or a blank leaf, and
    re-rendering it at higher resolution would find nothing twice."""
    assert needs_higher_resolution(_page()) is False


# Which pass wins is no longer decided by mean confidence: a recogniser that drops a hard line
# sounds surer about what is left. See tests/test_scanned_ocr_pass_choice.py.
