"""A run smaller than its block is drawn at its own size.

WHY THIS EXISTS: the writer gives a block one `font-size`, so a superscript marker, a footnote
reference or a formula fragment set at 6.8 pt inside a 10.2 pt block came out at 10.2 pt.

WHY THE DEFAULT IS ON: the setting was written off, shipped off, and only turned on after a two-arm
A/B over five recorded runs (both arms re-rendered, the setting the only difference - see
`docs/campaign/JOURNAL.md`): flattened boxes 104 -> 75 (-28%), squeezed boxes 1727 -> 1658 (69 fewer),
faithful boxes +53, and every audit criterion identical in 5/5 runs, including the L7 (text over text)
that the setting's own warning named as its risk. Turning a default on is a measured act; `test_the_
default_is_on` fails if someone flips it back without doing that measurement again.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core import tunables
from layoutkeep.core.docir import BBox, Span, Style
from layoutkeep.writers.pdf_writer import _FontResolver, _span_html

_KEY = "writer.inline_span_sizes"
_BOX = BBox(0.0, 0.0, 10.0, 6.0)


def test_the_default_is_on_and_only_a_measurement_turns_it_off() -> None:
    """The default was earned by the five-document A/B, not assumed; see the module docstring."""
    entry = tunables.definition(_KEY)
    assert entry.default is True, (
        "flipping this default back needs the same two-arm A/B - a re-rendered `off` arm, the "
        "criteria compared, and the numbers written into the journal"
    )


def _style(size: float) -> Style:
    return Style(font_family="Tinos", size=size, color="#000000")


def _span(size: float, text: str = "14") -> Span:
    return Span(text=text, bbox=_BOX, style=_style(size))


def test_the_smaller_run_keeps_its_own_size_when_the_setting_is_on() -> None:
    dominant = _style(10.2)
    was = tunables.get(_KEY)
    tunables.set_value(_KEY, True)
    try:
        html = _span_html(_span(6.8), dominant, _FontResolver("tr"))
    finally:
        tunables.set_value(_KEY, was)

    assert "font-size:6.80pt" in html, "the marker must be drawn at its own size"


def test_nothing_changes_while_the_setting_is_off() -> None:
    dominant = _style(10.2)
    was = tunables.get(_KEY)
    tunables.set_value(_KEY, False)
    try:
        html = _span_html(_span(6.8), dominant, _FontResolver("tr"))
    finally:
        tunables.set_value(_KEY, was)

    assert "font-size" not in html, "the default output must not move"


def test_a_run_at_the_block_size_gains_no_extra_markup() -> None:
    """Only a difference is worth a span: the same size is the block's own CSS."""
    dominant = _style(10.2)
    was = tunables.get(_KEY)
    tunables.set_value(_KEY, True)
    try:
        html = _span_html(_span(10.2, "ordinary"), dominant, _FontResolver("tr"))
    finally:
        tunables.set_value(_KEY, was)

    assert "font-size" not in html
