"""A line break inside a paragraph is a word separator, and has to survive as one.

Lines were handed to the provider joined by a bare newline, and OCR line text carries no
trailing space, so the boundary carried no separator at all. A model that collapses the newline
without putting anything in its place fuses the two words, and that is what came out of a real
page:

    ...guclen cok daha azdir.Tamponun amaci, buyuk miktarda guce ihtiyac duyan...
    Bu kitaptaikili degisken mantik tumleyeni icin prime kullanilirken...

Both are two words from either side of a line break, run together. The writer is not at fault -
it puts a <br> between a block's lines - the text was already fused before it got there.

So the provider is handed a paragraph: one space where the scan had a line break. The writer
re-wraps the translation to its box anyway, so the original break positions are not wanted; a
translation is a different length from its source, so keeping them would be wrong even if they
did survive.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style, block_source_text


def _block(*line_texts: str, styles: list[Style] | None = None) -> Block:
    styles = styles or [Style() for _ in line_texts]
    return Block(
        id="b1",
        role=BlockRole.BODY,
        bbox=BBox(0, 0, 200, 40),
        lines=[
            Line(spans=[Span(text=t, bbox=BBox(0, i * 10, 200, i * 10 + 8), style=styles[i])])
            for i, t in enumerate(line_texts)
        ],
    )


def test_a_line_break_becomes_a_space() -> None:
    text = block_source_text(_block("guclen cok daha azdir.", "Tamponun amaci, buyuk"))
    assert "azdir. Tamponun" in text
    assert "azdir.Tamponun" not in text


def test_a_line_that_already_ends_in_a_space_does_not_get_two() -> None:
    text = block_source_text(_block("Bu kitapta ", "ikili degisken"))
    assert "kitapta ikili" in text
    assert "  " not in text


def test_marked_text_keeps_the_separator_too() -> None:
    """The marked path builds the text run by run, so it needs the same treatment - a block with
    inline styling is exactly where a missing space is hardest to spot."""
    bold = Style(bold=True)
    plain = Style()
    text = block_source_text(_block("the first line", "second line here", styles=[plain, bold]))
    # The marker closes the first line, so the separator lands after it - what matters is that
    # the boundary carries one at all.
    assert "</0> second" in text, text
