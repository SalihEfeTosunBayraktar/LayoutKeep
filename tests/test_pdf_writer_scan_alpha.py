"""The scan buffer must come out three channels wide, whatever the source image carries.

WHY THIS EXISTS: the whitening pass rebuilt the scan's pixel buffer with a hard-coded three
channels. A page whose scan image carries alpha measures `n=4, alpha=1` in PyMuPDF, and PyMuPDF
*keeps* the alpha channel across a `csRGB` conversion, so the buffer stayed 4 components wide and
the reshape raised `cannot reshape array of size 32770400 into shape (3425, 2392, 3)`. That killed
the first chunk of the scanned Eleventh Development Plan: the process exited, the chunk wrote
neither an output nor a progress marker, the document was left a chunk short, and the merge refused
to build a document with a hole. This is the defect that the shipped comparison site's own README
would have called "one document missing".

The fixture is synthetic on purpose: the real page that reproduced it is a copyrighted government
plan and stays out of the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.writers.pdf_writer import _scan_pixels


def _rgb_pixmap(width: int = 8, height: int = 6) -> pymupdf.Pixmap:
    return pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)


def test_a_scan_with_alpha_becomes_three_channels() -> None:
    """`n=4, alpha=1` -> `H x W x 3`. The base reshaped to a hard-coded 3 and raised."""
    pixmap = pymupdf.Pixmap(_rgb_pixmap(), 1)  # add the alpha channel: n becomes 4
    assert pixmap.n == 4 and pixmap.alpha, "the fixture must carry alpha, or this test proves nothing"

    pixels = _scan_pixels(pixmap)

    assert pixels.shape == (pixmap.height, pixmap.width, 3)
    assert pixels.dtype == np.uint8
    assert len(pixels.tobytes()) == pixmap.width * pixmap.height * 3


def test_a_plain_scan_is_left_alone() -> None:
    pixels = _scan_pixels(_rgb_pixmap(8, 6))

    assert pixels.shape == (6, 8, 3)


def test_a_greyscale_scan_is_converted_to_rgb() -> None:
    """One component in, three out - the whitening pass works in RGB."""
    grey = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 8, 6), False)

    pixels = _scan_pixels(grey)

    assert pixels.shape == (6, 8, 3)
