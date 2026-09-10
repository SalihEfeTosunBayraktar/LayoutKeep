"""Tests for rotation-aware fitting: `Block.rotation` degrees CCW (core/docir.py) must shrink
the room fitting believes is available, because `bbox` stays axis-aligned even when the text
inside it doesn't (see core/docir.py's `Block.rotation` docstring and measure.py's
`rotated_run_length` / `rotated_block_fits` for the geometry).
"""

from __future__ import annotations

import os

import pytest

from layoutkeep.core.docir import BBox, Segment, Style
from layoutkeep.fitting.fit import FitLayer, fit_segment
from layoutkeep.fitting.measure import (
    TextMeasurer,
    make_measure_fn,
    rotated_block_fits,
    rotated_run_length,
)

ARIAL = r"C:\Windows\Fonts\arial.ttf"

pytestmark = pytest.mark.skipif(not os.path.isfile(ARIAL), reason="arial.ttf not present on this system")


def _measurer() -> TextMeasurer:
    return TextMeasurer(ARIAL)


# --------------------------------------------------------------------------------------
# Pure geometry - no fonts involved.
# --------------------------------------------------------------------------------------


def test_zero_rotation_run_length_is_plain_bbox_width():
    box = BBox(0, 0, 200, 50)
    assert rotated_run_length(box, 0.0, depth=10.0) == pytest.approx(200.0)


def test_ninety_degree_run_length_is_bbox_height_not_width():
    box = BBox(0, 0, 200, 50)
    assert rotated_run_length(box, 90.0, depth=10.0) == pytest.approx(50.0)


def test_negative_ninety_degree_behaves_like_ninety():
    # A line and its mirror-angle occupy the same axis-aligned footprint.
    box = BBox(0, 0, 200, 50)
    assert rotated_run_length(box, -90.0, depth=10.0) == pytest.approx(50.0)


def test_rotated_run_length_is_shorter_than_unrotated_for_the_same_box():
    box = BBox(0, 0, 200, 50)
    unrotated = rotated_run_length(box, 0.0, depth=10.0)
    rotated = rotated_run_length(box, 18.8, depth=10.0)
    assert rotated < unrotated


def test_rotated_block_fits_matches_run_length_at_the_boundary():
    box = BBox(0, 0, 200, 50)
    depth = 10.0
    length = rotated_run_length(box, 30.0, depth)
    assert rotated_block_fits(box, 30.0, length, depth)
    assert not rotated_block_fits(box, 30.0, length * 1.5, depth)


# --------------------------------------------------------------------------------------
# TextMeasurer.fits / make_measure_fn - real glyph metrics, no PyMuPDF.
# --------------------------------------------------------------------------------------


def test_measurer_reports_less_room_when_rotated():
    m = _measurer()
    style = Style(size=12.0)
    # A box the text fits in flat...
    box = BBox(0, 0, 220, 20)
    flat = m.fits("one two three four", style, box, rotation=0.0)
    tilted = m.fits("one two three four", style, box, rotation=25.0)
    assert flat.fits is True
    # ...but a 25 degree tilt eats into the same box's usable run, and can push the same text
    # to overflow even though nothing about the text or the box itself changed.
    assert tilted.fits is False


def test_ninety_degree_block_wraps_against_bbox_height():
    m = _measurer()
    style = Style(size=12.0)
    # Wide and short: as horizontal text this fits on one line easily. Rotated 90 degrees, the
    # available run is the box's height (20pt), which barely holds a couple of characters.
    box = BBox(0, 0, 500, 20)
    result = m.fits("one two three four five six", style, box, rotation=90.0)
    assert result.lines > 1


def test_make_measure_fn_end_to_end_with_rotation():
    m = _measurer()
    measure = make_measure_fn(m)
    style = Style(size=12.0)
    box = BBox(0, 0, 220, 20)
    segment = Segment(block_id="b1", source="src", target="one two three four")

    flat = fit_segment(segment, style, box, measure, rotation=0.0)
    tilted = fit_segment(segment, style, box, measure, rotation=25.0)

    assert flat.layer is FitLayer.AS_IS
    # Same text, same box, only the angle differs - fitting must not silently believe there is
    # still room once the box no longer matches the text's real orientation.
    assert tilted.layer is not FitLayer.AS_IS
