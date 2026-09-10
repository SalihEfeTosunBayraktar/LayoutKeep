"""Translating a project twice must not translate the translation.

Reopening a `.lkproj` and running it again handed the provider the text of the previous pass,
because the source of a segment came from the block's current text. With the test provider a
second pass produced "[tr] [tr] ..."; with a real provider it is a translation of a
translation, and nothing about the result looks like an error.
"""

from __future__ import annotations

from pathlib import Path

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Segment,
    Span,
    Style,
    apply_segments,
    load_project,
    save_project,
    segments_from_document,
)


def _block(block_id: str, text: str, top: float = 0.0) -> Block:
    return Block(
        id=block_id,
        role=BlockRole.BODY,
        bbox=BBox(0, top, 100, top + 20),
        lines=[
            Line(spans=[Span(text=text, bbox=BBox(0, top, 100, top + 20), style=Style(size=10))])
        ],
    )


def _document(text: str) -> Document:
    return Document(pages=[Page(number=1, width=595, height=842, blocks=[_block("b0", text)])])


def _translate(doc: Document, prefix: str) -> list[Segment]:
    segments = segments_from_document(doc)
    for segment in segments:
        segment.target = f"{prefix}{segment.source}"

    apply_segments(doc, segments)
    return segments


def test_a_second_pass_starts_from_the_original(tmp_path: Path) -> None:
    doc = _document("Form W-4")
    _translate(doc, "[tr] ")

    project = tmp_path / "job.lkproj"
    save_project(doc, project)
    again = segments_from_document(load_project(project))

    assert again[0].source == "Form W-4"


def test_the_original_survives_being_saved_and_reopened(tmp_path: Path) -> None:
    """`source_text` was on disk the whole time; it was simply never read back."""
    doc = _document("Form W-4")
    _translate(doc, "[tr] ")
    project = tmp_path / "job.lkproj"
    save_project(doc, project)

    reopened = load_project(project)

    assert reopened.pages[0].blocks[0].text == "[tr] Form W-4"
    assert reopened.pages[0].blocks[0].source_text == "Form W-4"


def test_a_third_pass_does_not_stack_either(tmp_path: Path) -> None:
    doc = _document("Form W-4")
    _translate(doc, "[tr] ")
    _translate(doc, "[de] ")

    assert doc.pages[0].blocks[0].text == "[de] Form W-4"
    assert segments_from_document(doc)[0].source == "Form W-4"


def test_context_comes_from_the_originals_too(tmp_path: Path) -> None:
    """Context is what the model reads to keep a passage consistent; feeding it the previous
    pass's output makes the second translation drift from the document it is translating."""
    doc = Document(
        pages=[
            Page(
                number=1,
                width=595,
                height=842,
                blocks=[_block("b0", "First line"), _block("b1", "Second line", top=30)],
            )
        ]
    )
    _translate(doc, "[tr] ")

    second = segments_from_document(doc)[1]

    assert second.context_before == "First line"
