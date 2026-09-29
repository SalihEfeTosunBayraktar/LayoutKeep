"""A space in a different font is not styled text, and must not become a marker.

Digital pilot, NIST SP 800-12 contents page: "5.2.1 Basic Components of Program Policy .... 27"
was sent as "5.2.1<0> </0>Basic Components ...": the gap after the section number is set in
another font, so it became an inline style run. The model dropped the marker - and the section
number with it: "5.2.1", "5.3.2" and "5.4.1" were missing from the translated page. A marker
around nothing but whitespace carries no formatting a reader could see.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style, block_source_text


def test_a_whitespace_run_in_another_style_gets_no_marker() -> None:
    body = Style(font_family="Helvetica", size=11.0)
    gap = Style(font_family="Helvetica-Bold", size=11.0)
    box = BBox(0, 0, 400, 12)
    spans = [
        Span(text="5.2.1", bbox=box, style=body),
        Span(text=" ", bbox=box, style=gap),
        Span(text="Basic Components of Program Policy .......... 27", bbox=box, style=body),
    ]
    block = Block(id="b", role=BlockRole.BODY, bbox=box, lines=[Line(spans=spans, bbox=box)])
    assert block_source_text(block) == "5.2.1 Basic Components of Program Policy .......... 27"


def test_real_bold_text_still_gets_its_marker() -> None:
    body = Style(font_family="Helvetica", size=11.0)
    bold = Style(font_family="Helvetica-Bold", size=11.0, bold=True)
    box = BBox(0, 0, 400, 12)
    spans = [Span(text="This is ", bbox=box, style=body), Span(text="bold", bbox=box, style=bold),
             Span(text=" text in a sentence that is long enough.", bbox=box, style=body)]
    block = Block(id="b", role=BlockRole.BODY, bbox=box, lines=[Line(spans=spans, bbox=box)])
    assert "<0>bold</0>" in block_source_text(block)
