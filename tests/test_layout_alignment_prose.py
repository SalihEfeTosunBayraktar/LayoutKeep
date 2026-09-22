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


def test_a_justified_paragraph_in_a_centred_column_is_justified() -> None:
    """Justified, not merely "left": the writer draws through an HTML box where `text-align:
    justify` is honoured, so recording it keeps the source's straight right edge. Recorded as
    "left" it came back ragged - the "alignments are lost in translation" the user reported."""
    lines = [BBox(44, 100 + i * 12, 278, 110 + i * 12) for i in range(5)] + [BBox(44, 160, 180, 170)]
    assert infer_alignment(BBox(44, 100, 278, 170), _NOVEL, lines) == "justify"


def test_a_first_line_indent_paragraph_is_justified() -> None:
    lines = [BBox(56, 100, 278, 110)] + [BBox(44, 112 + i * 12, 278, 122 + i * 12) for i in range(4)] + [BBox(44, 160, 150, 170)]
    assert infer_alignment(BBox(44, 100, 278, 170), _NOVEL, lines) == "justify"


def test_a_flush_left_paragraph_with_a_ragged_right_edge_stays_left() -> None:
    """The other half of the rule: ragged right edges are not justification."""
    lines = [BBox(44, 100, 250, 110), BBox(44, 112, 271, 122), BBox(44, 124, 233, 134), BBox(44, 136, 180, 146)]
    assert infer_alignment(BBox(44, 100, 278, 146), _NOVEL, lines) == "left"


def test_a_centred_block_whose_lines_shrink_is_not_called_justified() -> None:
    """A centred title's lines also get shorter towards the end; only where the last line *starts*
    separates it from a justified paragraph (the NASA cover title was drawn off centre without it)."""
    lines = [BBox(61, 100, 261, 110), BBox(111, 112, 211, 122)]
    assert infer_alignment(BBox(61, 100, 261, 122), _NOVEL, lines) == "center"


def test_a_right_aligned_two_line_block_stays_right() -> None:
    lines = [BBox(200, 100, 300, 110), BBox(240, 112, 300, 122)]
    assert infer_alignment(BBox(200, 100, 300, 122), _NOVEL, lines) == "right"


def test_centred_lines_of_different_widths_are_centred() -> None:
    lines = [BBox(61, 100, 261, 110), BBox(111, 112, 211, 122), BBox(86, 124, 236, 134)]
    assert infer_alignment(BBox(61, 100, 261, 134), _NOVEL, lines) == "center"


def test_right_aligned_lines_are_right() -> None:
    lines = [BBox(150, 100, 278, 110), BBox(200, 112, 278, 122), BBox(120, 124, 278, 134)]
    assert infer_alignment(BBox(120, 100, 278, 134), _NOVEL, lines) == "right"


def test_a_two_line_flush_left_title_is_not_justified() -> None:
    """PLOS ONE's title: 'Machine learning for modeling animal' over 'movement'. Its first line is
    the longest, so the right edge of the 'body' (one line) is trivially straight and the last line
    is short and starts at the left - every sign of justification, from a block that is not.
    Recorded as justify, the translation was stretched across the box with wide word gaps.

    Two lines cannot tell flush-left from justified; the costs are not equal (a justified pair
    drawn flush-left is barely visible, a flush-left title drawn justified is), so it stays left.
    """
    lines = [BBox(200, 109, 509, 128), BBox(200, 131, 290, 150)]
    assert infer_alignment(BBox(200, 109, 509, 150), 612.0, lines) == "left"
