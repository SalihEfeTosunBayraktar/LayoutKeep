"""A verdict reached during translation has to survive onto the block.

`segments_from_document` copies the block's flag onto the segment, but nothing copied it back.
Everything raised after the reader ran - a dropped literal, an ignored glossary term, inline
styling lost in translation, a segment the model handed back untranslated - was set on the
segment and the segment was then discarded. The review queue only ever showed what the reader
itself had flagged, which is why none of those failures were ever visible in the editor.
"""

from __future__ import annotations

import pytest

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
    apply_segments,
    segments_from_document,
)


def _doc(text: str) -> Document:
    bb = BBox(0, 0, 100, 20)
    style = Style(font_family="X", size=10)
    block = Block(
        id="b1",
        role=BlockRole.BODY,
        bbox=bb,
        lines=[Line(bbox=bb, spans=[Span(text=text, style=style, bbox=bb)])],
    )
    return Document(pages=[Page(number=1, width=200, height=200, blocks=[block])])


def test_a_flag_raised_during_translation_reaches_the_block() -> None:
    doc = _doc("They lived on treacle, said the Dormouse.")
    segments = segments_from_document(doc)
    segments[0].target = "Onlar pekmez üzerinde yaşarlardı."
    segments[0].needs_review = True
    segments[0].review_reason = "test sebebi"

    apply_segments(doc, segments)

    block = doc.pages[0].blocks[0]
    assert block.needs_review
    assert block.review_reason == "test sebebi"


def test_a_passthrough_is_visible_on_the_block_afterwards() -> None:
    """The end-to-end path: detector -> segment -> block -> what the editor reads."""
    from layoutkeep.providers.passthrough import flag_passthrough

    text = "They lived on treacle, said the Dormouse, after thinking a minute."
    doc = _doc(text)
    segments = segments_from_document(doc)
    segments[0].target = text

    assert flag_passthrough(segments) == 1
    apply_segments(doc, segments)

    block = doc.pages[0].blocks[0]
    assert block.needs_review
    assert "çevirmeden" in block.review_reason


def test_a_clean_translation_leaves_the_block_unflagged() -> None:
    doc = _doc("They lived on treacle, said the Dormouse.")
    segments = segments_from_document(doc)
    segments[0].target = "Onlar pekmez üzerinde yaşarlardı, dedi Sincap."

    apply_segments(doc, segments)

    assert not doc.pages[0].blocks[0].needs_review


def test_the_reason_survives_a_project_round_trip(tmp_path) -> None:
    from layoutkeep.core.docir import load_project, save_project

    doc = _doc("They lived on treacle, said the Dormouse.")
    segments = segments_from_document(doc)
    segments[0].target = "aynı"
    segments[0].needs_review = True
    segments[0].review_reason = "korunan değer çeviride yok"
    apply_segments(doc, segments)

    path = tmp_path / "p.lkproj"
    save_project(doc, path)
    reloaded = load_project(path)

    block = reloaded.pages[0].blocks[0]
    assert block.needs_review
    assert block.review_reason == "korunan değer çeviride yok"


@pytest.mark.parametrize("reader_flagged", [True, False])
def test_a_reader_flag_is_never_cleared_by_a_clean_translation(reader_flagged: bool) -> None:
    doc = _doc("They lived on treacle, said the Dormouse.")
    doc.pages[0].blocks[0].needs_review = reader_flagged
    segments = segments_from_document(doc)
    segments[0].target = "Onlar pekmez üzerinde yaşarlardı."

    apply_segments(doc, segments)

    assert doc.pages[0].blocks[0].needs_review is reader_flagged
