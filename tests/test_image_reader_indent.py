"""A paragraph whose first line is indented is still one paragraph.

Paragraph grouping compared each line's left edge to the line above and started a new paragraph
whenever they differed by more than 1.5 line heights. In a book that indents its first lines
that is every paragraph: measured on page 22 of `computer-systems-Architecture.pdf`, the opening
line sits at x=90.0 and the body at x=73.5 - a 16.6pt indent against an 8pt line height - so
each paragraph was cut into two blocks, an indented one-liner and the rest.

Everything the reader saw on that page follows from it:

  * 6 of 18 blocks began mid-sentence, so they could not be translated and came back English;
  * the two halves were fitted independently and got different type sizes, 6.60pt against
    8.04pt, which is the first line of a paragraph coming out visibly smaller than the rest;
  * being fitted independently, they also collided.

The rule is asymmetric, because indentation is: a new paragraph announces itself by starting
to the RIGHT of the line above. A line that starts to the LEFT is the body of a paragraph whose
first line was indented.
"""

from __future__ import annotations

from layoutkeep.ocr.engine import TextBox
from layoutkeep.readers.image_reader import _merge_lines_into_paragraphs

_HEIGHT = 8.0
_LEADING = 2.0


def _line(x0: float, index: int, text: str = "x") -> list[TextBox]:
    y0 = index * (_HEIGHT + _LEADING)
    return [TextBox(text=text, bbox=(x0, y0, x0 + 200.0, y0 + _HEIGHT), confidence=0.99)]


def _shape(paragraphs) -> list[int]:
    return [len(p) for p in paragraphs]


def test_an_indented_opening_line_stays_with_its_paragraph() -> None:
    """The measured case: first line indented 16.6pt, three body lines under it."""
    lines = [_line(90.0, 0), _line(73.4, 1), _line(73.4, 2), _line(73.4, 3)]
    assert _shape(_merge_lines_into_paragraphs(lines)) == [4]


def test_an_indent_after_body_text_starts_a_new_paragraph() -> None:
    """The other half of the rule - without this everything on the page becomes one block."""
    lines = [_line(73.4, 0), _line(73.4, 1), _line(90.0, 2), _line(73.4, 3)]
    assert _shape(_merge_lines_into_paragraphs(lines)) == [2, 2]


def test_a_big_vertical_gap_still_splits() -> None:
    """Indentation is now allowed to vary, so the vertical gap is the only thing left holding
    two unrelated paragraphs apart. It has to keep working."""
    far = [TextBox(text="x", bbox=(73.4, 400.0, 273.4, 408.0), confidence=0.99)]
    lines = [_line(73.4, 0), _line(73.4, 1), far]
    assert _shape(_merge_lines_into_paragraphs(lines)) == [2, 1]


def test_a_centred_line_above_a_paragraph_is_not_swallowed() -> None:
    """A centred caption sits far to the right of the body's left edge, so the leftward move
    into the paragraph below is much larger than an indent. It must not merge."""
    lines = [_line(150.0, 0), _line(73.4, 1), _line(73.4, 2)]
    shape = _shape(_merge_lines_into_paragraphs(lines))
    assert shape == [1, 2], shape


def test_a_margin_note_does_not_break_the_paragraph_it_annotates() -> None:
    """The remaining half of the page-22 failure.

    This book keeps a keyword in the left margin beside the paragraph it introduces - "OR",
    "inverter", "NAND". The note sits at x=10.8 against a body at x=73.4, level with the
    paragraph's second line, so sorting lines top-to-bottom drops it between the indented
    opening line and the body. Comparing each line only with the one immediately above it, that
    is the end of the paragraph: the opening line was left stranded as a one-line block and got
    its own type size.

    The note is not a continuation and not a new body paragraph either - it is a different
    column, and it must pass through without closing what it interrupts.
    """
    # The note sits BESIDE the paragraph, not on a row of its own - it is level with the text,
    # which is exactly why a top-to-bottom sort drops it into the middle of the paragraph. The
    # prose lines keep their normal pitch either side of it.
    note = [TextBox(text="OR", bbox=(10.8, 5.0, 30.8, 13.0), confidence=0.99)]
    lines = [_line(90.0, 0), note, _line(73.4, 1), _line(73.4, 2), _line(73.4, 3)]
    paragraphs = _merge_lines_into_paragraphs(lines)
    shapes = sorted(_shape(paragraphs))
    assert shapes == [1, 4], (
        f"expected the margin note alone and the four-line paragraph intact, got {shapes}"
    )
