"""Justified body text is not right-aligned, however narrow the page is.

`infer_alignment` called a block right-aligned when it ended near the right margin and had a
left margin worth more than 15% of the page. That is true of ordinary body text on a narrow
page: this book's pages are 318pt wide with a text column from x=74 to x=307, which leaves an
11pt right margin and a 74pt left one. The guard meant to catch full-width prose only fires at
80% of the page width, and the column is 73%.

Measured over six pages: 55 of 192 blocks came out "right", and 25 of them were prose blocks
over 80 characters. The reader had reported exactly this - "metinler bir kenara kayip
yaslanmis", the text has slid over and is pressed against one side - and it was still true
after alignment started being inferred at all; the inference was simply wrong.

The criterion that scales with the page instead of guessing at it: something pushed to the
right has a left margin much larger than the thing itself. A folio sitting in the right margin
is 20pt wide with 280pt of space to its left. A column of prose is 233pt wide with 74pt to its
left - the margin is smaller than the text, so the text is not pushed anywhere.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox
from layoutkeep.readers._layout import infer_alignment

PAGE = 318.0


def test_a_narrow_pages_body_column_is_not_right_aligned() -> None:
    """The measured case, verbatim: a 318pt page with its text column at 74-307."""
    assert infer_alignment(BBox(74, 100, 307, 140), PAGE) == "left"


def test_a_hanging_indent_body_block_is_not_right_aligned() -> None:
    """Exercise lists indent further, which makes the left margin larger still."""
    assert infer_alignment(BBox(103, 100, 307, 130), PAGE) == "left"


def test_a_folio_in_the_right_margin_is_still_right_aligned() -> None:
    """The case the rule exists for, and the reason it cannot just be deleted."""
    assert infer_alignment(BBox(288, 20, 308, 30), PAGE) == "right"


def test_a_centred_caption_is_still_centred() -> None:
    assert infer_alignment(BBox(100, 200, 218, 212), PAGE) == "center"


# Digital pilot, The Time Machine and Think Python: justified body paragraphs came out CENTRED.
# Their text column sits in the middle of the page (a 322pt page, text 44-278), so a rule that
# only compares a block with the page could not tell a centred column of prose from a centred
# title - and once the writer honoured alignment, every paragraph was centred. The lines say
# which it is: justified or flush-left lines share a left edge; centred lines share a centre and
# not a left edge.


_NOVEL = 322.0


def test_a_justified_paragraph_in_a_centred_column_is_left() -> None:
    lines = [BBox(44, 100 + i * 12, 278, 110 + i * 12) for i in range(5)] + [BBox(44, 160, 180, 170)]
    assert infer_alignment(BBox(44, 100, 278, 170), _NOVEL, lines) == "left"


def test_a_first_line_indent_paragraph_is_left() -> None:
    lines = [BBox(56, 100, 278, 110)] + [BBox(44, 112 + i * 12, 278, 122 + i * 12) for i in range(4)] + [BBox(44, 160, 150, 170)]
    assert infer_alignment(BBox(44, 100, 278, 170), _NOVEL, lines) == "left"


def test_centred_lines_of_different_widths_are_centred() -> None:
    lines = [BBox(61, 100, 261, 110), BBox(111, 112, 211, 122), BBox(86, 124, 236, 134)]
    assert infer_alignment(BBox(61, 100, 261, 134), _NOVEL, lines) == "center"


def test_right_aligned_lines_are_right() -> None:
    lines = [BBox(150, 100, 278, 110), BBox(200, 112, 278, 122), BBox(120, 124, 278, 134)]
    assert infer_alignment(BBox(120, 100, 278, 134), _NOVEL, lines) == "right"
