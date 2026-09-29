"""Boxes at the same height are only the same line if they are also close together.

`_merge_boxes_into_lines` existed to rejoin a text line that OCR split in the middle (an
obstruction, a wide inter-word gap). It grouped on vertical overlap alone, with no limit on
horizontal distance, so anything sharing a y-band became one line - including things that are
plainly not: the label columns either side of a figure, a table row's cells, two columns of text.

Measured on page 61 of `computer-systems-Architecture.pdf`, where the failure is visible:

    '46' + 'CHAPTER TWO Digital Components'   gap 0.79x line height   a real running header
    'decoder' + 'D0'                          gap 2.79x               opposite sides of a figure
    'A0' + '2^0' + 'D1'                       gap 5.88x, 4.84x        a diagram's label columns

The legitimate join sits at 0.79 and every bogus one at 2.79 or more, so the threshold goes
between them. Getting this wrong is not cosmetic: the welded line's bounding box spanned the
whole figure, which made the block that contains it span the figure too, and the pdf writer
then painted over the diagram to clear the source text.
"""

from __future__ import annotations

from layoutkeep.ocr.engine import TextBox
from layoutkeep.readers.image_reader import _merge_boxes_into_lines

_HEIGHT = 25.0


def _box(text: str, x0: float, y0: float = 100.0, width: float = 40.0) -> TextBox:
    return TextBox(text=text, bbox=(x0, y0, x0 + width, y0 + _HEIGHT), confidence=0.99)


def _texts(lines: list[list[TextBox]]) -> list[list[str]]:
    return [[b.text for b in line] for line in lines]


def test_a_split_line_is_rejoined() -> None:
    """The case the merge was written for: one line broken mid-way, a small gap."""
    left = _box("CHAPTER TWO", x0=0)
    right = _box("Digital Components", x0=40 + _HEIGHT * 0.8)
    assert _texts(_merge_boxes_into_lines([left, right])) == [["CHAPTER TWO", "Digital Components"]]


def test_far_apart_boxes_stay_separate_lines() -> None:
    """A figure's left and right label columns share a y-band but are not one line."""
    left = _box("A0", x0=0)
    middle = _box("2^0", x0=40 + _HEIGHT * 5.9)
    right = _box("D1", x0=40 + _HEIGHT * 5.9 + 40 + _HEIGHT * 4.8)
    lines = _merge_boxes_into_lines([left, middle, right])
    assert _texts(lines) == [["A0"], ["2^0"], ["D1"]]


def test_separated_boxes_keep_their_own_narrow_boxes() -> None:
    """The point of splitting them: each line's bbox must stay over its own text, because the
    block bbox is built from these and the writer paints that box over the scan."""
    left = _box("A0", x0=0)
    right = _box("D1", x0=500)
    lines = _merge_boxes_into_lines([left, right])
    for line in lines:
        span = max(b.bbox[2] for b in line) - min(b.bbox[0] for b in line)
        assert span < 100, "a line still spans the gap between two separate labels"
