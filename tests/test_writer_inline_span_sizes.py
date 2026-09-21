"""A run smaller than its block is drawn at its own size - but only when the setting is on.

WHY THIS EXISTS: the writer gives a block one `font-size`, so a superscript marker, a footnote
reference or a formula fragment set at 6.8 pt inside a 10.2 pt block came out at 10.2 pt. Measured on
`arxiv_19145`: 48 of 145 blocks carry a run of a different size, and carrying them drops the per-box
`flattened` count from 7 to 4 while L7 (text drawn over text, the risk the setting carries) stays at 0.
The default is off: one document's measurement is what earns the A/B, not what flips a default.
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
