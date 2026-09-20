"""The measurement and the drawing agree about line height.

The seam this guards: `fitting/measure.py` has always read `style.line_height` when deciding
whether a text fits its box, but `pdf_writer`'s CSS never wrote it - so a block whose style named
a leading was *measured* against that leading and *drawn* with the engine's own. Nothing noticed
because no reader fills the field in today; it becomes live the moment the fitting ladder starts
tightening the leading to rescue an overflowing translation (the largest single review-flag class
in the book run: 352 of 6,570 blocks). This test holds both halves: the measurement honours the
field, and the CSS carries it.
"""

from __future__ import annotations

from layoutkeep.core.docir import Block, BBox, Document, Line, Page, Span, Style
from layoutkeep.fitting.measure import make_measure_fn  # noqa: F401  (used by _measure)


def _block_with_leading(line_height: float | None) -> Block:
    style = Style(font_family="Helvetica", size=11.0, line_height=line_height)
    lines = [
        Line(bbox=BBox(0, 10 * index, 200, 10 * index + 10), spans=[Span(text="x" * 40, bbox=BBox(0, 0, 200, 10), style=style)])
        for index in range(6)
    ]
    return Block(id="b1", role="paragraph", bbox=BBox(0, 0, 200, 60), lines=lines)


def _document(block: Block) -> Document:
    return Document(pages=[Page(number=1, width=612, height=792, blocks=[block])])


def _measure():
    """A real glyph measurer over the bundled font, the same one the fitting layer uses."""
    from pathlib import Path as _Path

    from layoutkeep.fitting.measure import TextMeasurer

    font = _Path(__file__).resolve().parents[1] / "src/layoutkeep/assets/fonts/Carlito-Regular.ttf"
    return make_measure_fn(TextMeasurer(font))


def test_a_named_line_height_changes_what_fits() -> None:
    """The measurement is the thing the ladder decides with, so it has to see the field."""
    measure = _measure()
    tall = _block_with_leading(18.0)
    tight = _block_with_leading(11.0)
    box = BBox(0, 0, 200, 62)  # room for six lines at 11pt leading, not at 18pt

    # Long enough to wrap into several lines: a one-line text fits whatever the leading is, which
    # is what the first version of this test measured (it passed for the wrong reason).
    text = ("the quick brown fox jumps over the lazy dog and keeps going for a while " * 3).strip()
    fits_tall, _ = measure(text, tall.dominant_style(), box, scale_low=1.0)
    fits_tight, _ = measure(text, tight.dominant_style(), box, scale_low=1.0)

    assert fits_tight, "six lines at an 11pt leading must fit a 62pt box"
    assert not fits_tall, "the same six lines at an 18pt leading must not"


def test_the_writer_writes_the_named_line_height_into_the_css() -> None:
    from layoutkeep.writers.pdf_writer import _FontResolver, _css_for_block

    block = _block_with_leading(12.5)
    resolver = _FontResolver("tr")
    css = _css_for_block(block, resolver)

    assert "line-height: 12.50pt" in css, css


def test_a_block_without_a_named_line_height_leaves_the_css_alone() -> None:
    """Every block in the repository today: the rule must not appear, or the engine's own
    leading (which the writer calibrated against, `writer_line_height_ratio`) would be
    overridden for every paragraph in every document."""
    from layoutkeep.writers.pdf_writer import _FontResolver, _css_for_block

    block = _block_with_leading(None)
    resolver = _FontResolver("tr")
    css = _css_for_block(block, resolver)

    assert "line-height" not in css, css
