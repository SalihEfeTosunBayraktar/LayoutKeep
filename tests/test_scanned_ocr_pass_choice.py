"""Between two OCR passes, the better one is the one that recovered more text.

A page read badly at the cheap resolution gets a second pass at a higher one, and both are kept
so the higher resolution has to earn its place. The winner was picked on mean confidence, which
is the wrong quantity: a recogniser that drops a hard line scores higher on what is left, so
"more confident" and "read more" are not the same verdict and they disagree in practice.

Measured on both documents in hand:

    book page 54     200 DPI: 1687 chars @ 0.945    300 DPI: 1845 @ 0.962   agree
    book page 451    200 DPI: 1746 chars @ 0.954    300 DPI: 1681 @ 0.977   DISAGREE
    notes page 2     200 DPI:  362 chars @ 0.848    300 DPI:  346 @ 0.843   agree
    notes page 3     200 DPI:  438 chars @ 0.880    300 DPI:  433 @ 0.889   DISAGREE
    notes page 5     200 DPI:   72 chars @ 0.871    300 DPI:   86 @ 0.951   agree

On book page 451 the confidence rule chose the pass that read 65 characters fewer. Weighting
each block's characters by the confidence in them - the amount of text we actually believe -
picks correctly in all five, including the two where the rules disagree.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Page, Span, Style
from layoutkeep.readers.image_reader import expected_characters


def _page(*blocks: tuple[str, float]) -> Page:
    page = Page(number=1, width=318.0, height=424.0, source_ref="0")
    style = Style()
    page.blocks = [
        Block(
            id=f"b{i}",
            role=BlockRole.BODY,
            bbox=BBox(0, i * 10, 200, i * 10 + 8),
            lines=[Line(spans=[Span(text=text, bbox=BBox(0, 0, 200, 8), style=style)])],
            confidence=confidence,
        )
        for i, (text, confidence) in enumerate(blocks)
    ]
    return page


def test_more_text_beats_more_confidence() -> None:
    """Book page 451, in miniature: the second pass is surer about less."""
    cheap = _page(("A" * 1746, 0.954))
    dearer = _page(("A" * 1681, 0.977))
    assert expected_characters(cheap) > expected_characters(dearer)


def test_a_genuinely_better_pass_still_wins() -> None:
    """Book page 54: the second pass read more AND believed it more."""
    cheap = _page(("A" * 1687, 0.945))
    dearer = _page(("A" * 1845, 0.962))
    assert expected_characters(dearer) > expected_characters(cheap)


def test_a_small_page_read_better_still_wins() -> None:
    """Notes page 5: little text either way, but the second pass got more of it."""
    cheap = _page(("A" * 72, 0.871))
    dearer = _page(("A" * 86, 0.951))
    assert expected_characters(dearer) > expected_characters(cheap)


def test_confidence_still_counts() -> None:
    """It is not a character count: the same amount of text, believed less, is worth less."""
    sure = _page(("A" * 100, 0.99))
    unsure = _page(("A" * 100, 0.50))
    assert expected_characters(sure) > expected_characters(unsure)


def test_an_empty_page_scores_nothing() -> None:
    assert expected_characters(_page()) == 0.0
