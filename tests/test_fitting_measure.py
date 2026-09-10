"""Synthetic measurement tests: known text + known font -> expected line count/width.

Uses real system fonts (Windows ships Arial/Times New Roman) so the numbers come from actual
glyph metrics via fontTools, not from a character-count guess.
"""

from __future__ import annotations

import os

import pytest

from layoutkeep.core.docir import BBox, Segment, Style
from layoutkeep.fitting.fit import FitLayer, fit_segment
from layoutkeep.fitting.measure import TextMeasurer, make_measure_fn

ARIAL = r"C:\Windows\Fonts\arial.ttf"

pytestmark = pytest.mark.skipif(not os.path.isfile(ARIAL), reason="arial.ttf not present on this system")


def _measurer() -> TextMeasurer:
    return TextMeasurer(ARIAL)


def test_char_width_matches_raw_hmtx_advance():
    # Ground truth read independently from the font's own hmtx/head tables: 'H' advance is
    # 1479 font units at unitsPerEm=2048 (verified directly against C:\Windows\Fonts\arial.ttf).
    m = _measurer()
    size = 12.0
    expected = 1479 / 2048 * size
    assert m.char_width("H", size) == pytest.approx(expected, abs=1e-6)


def test_missing_glyph_has_zero_width():
    m = _measurer()
    assert m.char_width("\u2603", 12.0) == 0.0  # snowman is not in Arial's cmap


def test_wrap_lines_never_breaks_when_box_is_wide_enough():
    m = _measurer()
    lines = m.wrap_lines("one two three four five", 12.0, max_width=100_000)
    assert lines == ["one two three four five"]


def test_wrap_lines_breaks_every_word_when_box_is_too_narrow():
    m = _measurer()
    lines = m.wrap_lines("one two three four five", 12.0, max_width=0.001)
    assert lines == ["one", "two", "three", "four", "five"]


def test_wrap_lines_breaks_at_the_exact_measured_boundary():
    m = _measurer()
    size = 12.0
    # Build a box that fits exactly the first two words - a genuine black-box test of wrapping
    # logic against widths this same measurer reports for the individual words.
    max_width = m.text_width("aaaa bbbb", size)
    lines = m.wrap_lines("aaaa bbbb cccc", size, max_width)
    assert lines == ["aaaa bbbb", "cccc"]


def test_respects_existing_newlines_as_hard_breaks():
    m = _measurer()
    lines = m.wrap_lines("first\nsecond", 12.0, max_width=100_000)
    assert lines == ["first", "second"]


def test_fits_reports_expected_line_count_and_overflow():
    m = _measurer()
    style = Style(size=12.0)
    narrow_box = BBox(0, 0, 40, 200)  # narrow width forces multiple lines, tall enough to fit
    result = m.fits("one two three four five", style, narrow_box)
    assert result.lines is not None and result.lines > 1
    assert result.fits is True

    short_box = BBox(0, 0, 40, 10)  # not tall enough for the wrapped lines
    result2 = m.fits("one two three four five", style, short_box)
    assert result2.fits is False


def test_char_budget_scales_with_box_size():
    m = _measurer()
    style = Style(size=12.0)
    small = BBox(0, 0, 50, 20)
    large = BBox(0, 0, 500, 200)
    assert m.char_budget(style, large) > m.char_budget(style, small)


def test_make_measure_fn_matches_the_pdf_writer_seam_end_to_end():
    """make_measure_fn -> fit_segment, using only real fontTools metrics, no PyMuPDF."""
    m = _measurer()
    measure = make_measure_fn(m)
    style = Style(size=12.0)
    big_box = BBox(0, 0, 500, 200)

    segment = Segment(block_id="b1", source="src", target="one two three")
    result = fit_segment(segment, style, big_box, measure)
    assert result.layer is FitLayer.AS_IS

    tiny_box = BBox(0, 0, 5, 5)
    result2 = fit_segment(segment, style, tiny_box, measure)
    assert result2.layer is FitLayer.OVERFLOW
