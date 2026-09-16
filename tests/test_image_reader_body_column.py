"""The body column is where the LONG lines start, not the median of every line.

Paragraph grouping treats a line far left of the body column as another column - a margin
keyword beside the paragraph it introduces - so it becomes its own block and does not end the
paragraph it interrupted. That needs to know where the body column is, and it used the median
left edge over all of a page's lines.

That works on a page of prose and fails on anything else, because figure labels, grid cells and
table entries sit scattered to the right and drag the median with them. Measured at 200 DPI,
against a body column at 205px:

    page   median-all   long-lines only
      28          308               206    figure heavy
     451          300               205    figure heavy
     121          377               204    tables
      22          206               207    prose with margin notes
     251          204               204    plain prose

On pages 28 and 451 the median landed 100px right of the body, so twenty real body lines were
each mistaken for a margin note - which is why those pages came back with every line of every
paragraph as its own block: 17 and 14 blocks beginning mid-sentence.

Body lines are long and labels are short, so the body column is the median left edge among
lines at least half as wide as the page's widest. That is measured against the page's own
widest line, so it does not need to know anything about this book.
"""

from __future__ import annotations

from layoutkeep.ocr.engine import TextBox
from layoutkeep.readers.image_reader import _merge_lines_into_paragraphs

_H = 8.0


def _line(x0: float, top: float, width: float, text: str = "x") -> list[TextBox]:
    return [TextBox(text=text, bbox=(x0, top, x0 + width, top + _H), confidence=0.99)]


def _shape(paragraphs) -> list[int]:
    return [len(p) for p in paragraphs]


def test_scattered_figure_labels_do_not_move_the_body_column() -> None:
    """Page 28's shape: a paragraph of long lines, plus short labels scattered to the right.

    Counting every line equally, the median left edge lands among the labels and every body
    line looks like it sits in another column.
    """
    body = [_line(74.0, 100.0 + i * 10, 230.0) for i in range(4)]
    labels = [
        _line(150.0, 200.0, 20.0),
        _line(200.0, 210.0, 18.0),
        _line(260.0, 220.0, 22.0),
        _line(240.0, 230.0, 16.0),
        _line(280.0, 240.0, 20.0),
    ]
    paragraphs = _merge_lines_into_paragraphs([*body, *labels])
    shapes = _shape(paragraphs)
    assert shapes[0] == 4, (
        f"the four body lines should be one paragraph, got {shapes} - each body line was taken "
        f"for a margin note"
    )


def test_a_margin_note_is_still_recognised() -> None:
    """The behaviour this must not lose: a keyword in the left margin, beside the body."""
    note = _line(10.0, 105.0, 20.0, text="OR")
    body = [_line(74.0, 100.0, 230.0), _line(74.0, 110.0, 230.0), _line(74.0, 120.0, 230.0)]
    paragraphs = _merge_lines_into_paragraphs([body[0], note, body[1], body[2]])
    assert sorted(_shape(paragraphs)) == [1, 3], _shape(paragraphs)


def test_a_page_of_only_short_lines_still_groups() -> None:
    """A table of contents or an index has no long lines at all; the widest one on the page is
    then the reference, and nothing should be thrown out as another column."""
    lines = [_line(74.0, 100.0 + i * 10, 40.0) for i in range(3)]
    assert _shape(_merge_lines_into_paragraphs(lines)) == [3]
