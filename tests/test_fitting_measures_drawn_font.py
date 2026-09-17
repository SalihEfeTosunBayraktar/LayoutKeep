"""Fitting measures with the face the writer will draw, not with a generic stand-in.

Held-out PLOS ONE article: eight one-line blocks lost their last words. The source face (Minion) is
serif; with no font file resolved, fitting measured the Turkish line in the generic serif - Times,
narrow - and found it fit on one line at full size, while the writer drew it in the resolved Noto
Serif, 29% wider. The line wrapped, the box had 4 pt to spare below it, and the second line was not
drawn. Measured the same sentence at 10 pt: Times 260.5 pt, Noto Serif 335.8 pt.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Segment, Span, Style
from layoutkeep.fitting.pdf_pass import fit_pdf_pass

_TURKISH = "Konum için koloni düzeyindeki model aşağıdaki denklemle verilmiştir"


def _block(block_id: str, text: str, top: float, family: str) -> Block:
    box = BBox(72, top, 352, top + 10)  # 280 pt wide: one line in Times, two in Noto Serif
    style = Style(font_family=family, size=10.0, serif=True)
    return Block(
        id=block_id, role=BlockRole.BODY, bbox=box,
        lines=[Line(spans=[Span(text=text, bbox=box, style=style)], bbox=box)], source_text=text,
    )


def test_a_line_that_wraps_in_the_drawn_face_does_not_fit_as_it_is() -> None:
    line = _block("line", _TURKISH, 200, "URWPalladioL-Roma")
    # The PLOS geometry: a 10 pt line box, the next block 6 pt below - room for the slack, not a line.
    below = _block("below", "x = y + z", 216, "URWPalladioL-Roma")
    doc = Document(target_lang="tr", pages=[Page(number=1, width=612, height=792, blocks=[line, below])])
    segment = Segment(block_id="line", source="The colony level model for location is given by", target=_TURKISH)
    verdicts = []

    fit_pdf_pass(
        doc, [segment], retranslate=lambda seg, budget: seg.target, target_lang="tr",
        on_fitted=lambda seg, block, result: verdicts.append(result),
    )

    assert verdicts and (verdicts[0].scale < 1.0 or verdicts[0].needs_review), verdicts
