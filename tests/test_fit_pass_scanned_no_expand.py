"""On a scanned page the fitting pass must not ask for a LONGER translation.

The under-fill direction exists for the EN->TR 0.64x tail: a translation that leaves its box
much emptier than the source filled it reads as a hole in the page, so a longer rendering is
requested. That reasoning needs the box to be the frame the source text actually filled.

On a scanned page it is not. The box is an OCR artifact - the detector's idea of where the
glyphs were - widened further by `image_reader._grant_blank_paper`, which deliberately hands
the block blank paper so a longer language has somewhere to go. Measuring fill against that box
asks the model to pad the text until it covers space the original never used, which invents
content: expansion measured 1.47x on page 28 of `computer-systems-Architecture.pdf`, against
0.93-1.12x for honest EN->TR. 18% of prose blocks on a six-page sample looked under-filled
purely because their boxes had been grown.

`char_budget=None` is the existing, documented way to silence that direction (see
`_measurer_for`: a font that will not load disables it the same way). The overflow direction is
unaffected - it falls back to a length-based budget - so text that does not fit is still
shortened.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Segment, Span, Style
from layoutkeep.fitting.pdf_pass import fit_pdf_pass


def _doc(*, scanned: bool) -> tuple[Document, Segment]:
    style = Style(font_family="Arial", size=10.0)
    block = Block(
        id="b1",
        role=BlockRole.BODY,
        # A box far larger than the text needs: maximum invitation to the expand direction.
        bbox=BBox(0, 0, 400, 200),
        lines=[Line(spans=[Span(text="Kisa bir cumle.", bbox=BBox(0, 0, 80, 12), style=style)])],
    )
    page = Page(number=1, width=600.0, height=800.0, source_ref="0")
    page.blocks = [block]
    page.scanned = scanned
    doc = Document(source_path="x.pdf", source_format="pdf", target_lang="tr")
    doc.pages = [page]
    segment = Segment(block_id="b1", source="A short sentence.", target="Kisa bir cumle.")
    return doc, segment


def _run(*, scanned: bool) -> list[int]:
    """Returns the budgets the fitting pass asked for; empty means it asked for nothing."""
    asked: list[int] = []

    def retranslate(segment: Segment, budget: int) -> str:
        asked.append(budget)
        return segment.target

    doc, segment = _doc(scanned=scanned)
    fit_pdf_pass(doc, [segment], retranslate=retranslate, target_lang="tr")
    return asked


def test_a_scanned_page_is_never_asked_to_pad() -> None:
    assert _run(scanned=True) == [], (
        "the pass asked for a longer translation to fill a box that OCR invented"
    )


def test_an_ordinary_page_still_expands() -> None:
    """The guard must be limited to scanned pages - this is the behaviour it must not remove."""
    assert _run(scanned=False), "the under-fill direction stopped working on ordinary PDFs"
