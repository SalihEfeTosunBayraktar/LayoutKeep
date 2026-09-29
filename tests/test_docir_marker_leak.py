"""Inline markers must never reach the page, whatever the model sends back.

The pipeline wraps runs that differ from a block's dominant style in numbered markers -
`a <0>bold</0> word` - and the provider is told to reproduce them. When the reply's markers
cannot be mapped back, the text is put down as plain and the block is flagged, with the markers
stripped first so they do not leak.

Except the stripping was conditional on the block having had inline styling to begin with:

    clean = _MARKER_RE.sub("", text) if styles else text

A block with no styled runs was never given markers, so any that come back are the model's
invention - and that is exactly the branch that passed the text through untouched. Off page 54
of the finished output, as readable text on the page:

    <0>Carpimlarin toplami</0> formu ve <1>Toplamlarin carpimi</1> formu.

Stripping is now unconditional. `block_source_text` already refuses to add markers to text that
already looks like markers, so a document that genuinely contains "<0>" is not made worse by
this - and a stray marker in the output is worse than a lost bit of styling either way.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style, _replace_block_text


def _block(*, styled: bool) -> Block:
    plain = Style(font_family="Arial", size=10.0)
    spans = [Span(text="a plain line", bbox=BBox(0, 0, 100, 10), style=plain)]
    if styled:
        spans.append(
            Span(text=" bold bit", bbox=BBox(100, 0, 160, 10), style=Style(
                font_family="Arial", size=10.0, bold=True))
        )
    return Block(
        id="b1",
        role=BlockRole.BODY,
        bbox=BBox(0, 0, 200, 20),
        lines=[Line(spans=spans, bbox=BBox(0, 0, 200, 20))],
    )


def _text_of(block: Block) -> str:
    return "".join(s.text for line in block.lines for s in line.spans)


def test_markers_are_stripped_from_an_unstyled_block() -> None:
    """The leak: nothing asked for markers here, so whatever came back must not be shown."""
    block = _block(styled=False)
    _replace_block_text(block, "<0>Carpimlarin toplami</0> formu ve <1>Toplamlarin carpimi</1>")
    text = _text_of(block)
    assert "<0>" not in text and "</0>" not in text and "<1>" not in text, text
    assert "Carpimlarin toplami" in text


def test_a_styled_block_with_unusable_markers_is_still_cleaned() -> None:
    """The case that already worked - it must keep working."""
    block = _block(styled=True)
    faithful = _replace_block_text(block, "<7>mismatched marker</7> text")
    text = _text_of(block)
    assert "<7>" not in text, text
    assert faithful is False, "losing the styling has to be reported, not hidden"


def test_a_clean_reply_still_maps_its_styling() -> None:
    """And the happy path is untouched: usable markers become real spans, not stripped text."""
    block = _block(styled=True)
    faithful = _replace_block_text(block, "duz satir <0>kalin parca</0>")
    assert faithful is True
    assert "<0>" not in _text_of(block)
    assert any(s.style.bold for line in block.lines for s in line.spans)
