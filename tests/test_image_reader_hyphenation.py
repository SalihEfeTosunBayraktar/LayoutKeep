"""A word split across a scanned line break has to be put back together.

pdf_reader joins `iden-` + `tities` into `identities` before anything is translated.
image_reader had no hyphenation handling at all - not one mention of a hyphen in the file - so
on every scanned page the halves stayed apart, and the second half became a segment of its own
beginning mid-word. A model cannot translate `tities in the table can be proven by...`, so it
came back as-is.

That is what page 24 of the finished output looks like, and what the report flagged:

    Tablo 1-1, Boole cebirinin en temel ozdesliklerini listeler. Tum ozdes-
    The identities in the table can be proven by means of truth tables. The first eight id

The paragraph changes language mid-sentence, right at the hyphen. Reported as "hem cevrilmis
hem cevrilmemis bir kisim var" - part translated, part not.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Line, Span, Style
from layoutkeep.readers._layout import join_hyphenation


def _line(*texts: str) -> Line:
    style = Style()
    return Line(
        spans=[Span(text=t, bbox=BBox(0, 0, 10, 10), style=style) for t in texts],
        bbox=BBox(0, 0, 10, 10),
    )


def _texts(lines: list[Line]) -> list[str]:
    return [line.text for line in lines]


def test_a_split_word_is_rejoined() -> None:
    lines = [_line("Table 1-1 lists the most basic iden-"), _line("tities of Boolean algebra.")]
    join_hyphenation(lines)
    assert " ".join(_texts(lines)) == "Table 1-1 lists the most basic identities of Boolean algebra."


def test_a_real_hyphenated_word_is_left_alone() -> None:
    """`self-` followed by a capital is not a broken word - it is a line that happens to end in
    a hyphen, and gluing it would invent a word that was never there."""
    lines = [_line("a self-"), _line("Contained unit")]
    join_hyphenation(lines)
    assert len(lines) == 2


def test_a_dash_after_a_space_is_not_a_word_break() -> None:
    lines = [_line("the operands -"), _line("and the result")]
    join_hyphenation(lines)
    assert len(lines) == 2


def _placed(text: str, top: float) -> Line:
    style = Style()
    return Line(
        spans=[Span(text=text, bbox=BBox(74, top, 308, top + 8), style=style)],
        bbox=BBox(74, top, 308, top + 8),
    )


def test_rejoining_keeps_the_second_lines_place_on_the_page() -> None:
    """Book pages 28 and 451, translated: the line after a break stayed visible in English.

    The whole of the next line used to be folded into the hyphenated one and the next line
    deleted, while the surviving line kept its own one-line box. The block's box is the union of
    its lines, so it stopped a line short, the writer painted out only that box, and the source
    line `ing term it represents is A'BC'D.` stayed on the page under the translation.

    Only the word fragment moves; the rest of the second line keeps its line and its box.
    """
    lines = [
        _placed("variables. The binary number contains the four bits 0101, and the correspond-", 335),
        _placed("ing term it represents is A'BC'D.", 343),
    ]
    join_hyphenation(lines)
    assert " ".join(_texts(lines)) == (
        "variables. The binary number contains the four bits 0101, and the corresponding "
        "term it represents is A'BC'D."
    )
    assert max(line.bbox.y1 for line in lines) == 351


def test_a_second_line_that_was_only_the_fragment_leaves_its_box_behind() -> None:
    lines = [_placed("the correspond-", 335), _placed("ing", 343)]
    join_hyphenation(lines)
    assert _texts(lines) == ["the corresponding"]
    assert lines[0].bbox.y1 == 351
