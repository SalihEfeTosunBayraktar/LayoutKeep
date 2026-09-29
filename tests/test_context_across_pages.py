"""Context crosses the page boundary: the first block of a page is asked with the last of the one before.

Bağlam sayfa sınırını aşar: bir sayfanın ilk bloğu, önceki sayfanın son bloğuyla birlikte sorulur.

Roadmap item 7 ("cross-page context") proposed adding the previous chunk's last blocks to the request.
In the product that already holds - segments are built over the whole document before any batching
or page range (D-023) - and this file pins it, so a change that builds segments per page cannot take
it away silently.
"""

from __future__ import annotations

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
    segments_from_document,
)


def _block(block_id: str, text: str) -> Block:
    box = BBox(x0=0.0, y0=0.0, x1=100.0, y1=10.0)
    span = Span(text=text, bbox=box, style=Style(size=10.0))
    return Block(id=block_id, role=BlockRole.BODY, bbox=box, lines=[Line(bbox=box, spans=[span])])


def test_the_first_block_of_a_page_sees_the_last_block_of_the_page_before() -> None:
    doc = Document(source_path="x.pdf", source_format="pdf", pages=[
        Page(number=1, width=200, height=200, blocks=[_block("a", "The committee met on Monday."),
                                                      _block("b", "It adopted the")]),
        Page(number=2, width=200, height=200, blocks=[_block("c", "report without changes.")]),
    ])

    segments = {segment.block_id: segment for segment in segments_from_document(doc)}

    assert segments["c"].context_before == "It adopted the"
    assert segments["b"].context_after == "report without changes."
