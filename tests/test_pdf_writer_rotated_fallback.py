"""A rotated line that cannot be found again must still be redacted, not crash the page.

Campaign digital pilot: 7 of 10 NIST SP 800-12 pages produced no output at all - "Point: bad
args". Each page carries a line of text rotated 90 degrees in its margin. When `search_for` cannot
find a line again, the writer falls back to redacting the line's whole box, built as
`pymupdf.Quad(rect)` - which this PyMuPDF rejects. The fallback, written for the rare case, had
never run; the page was lost instead of being written.
"""

from __future__ import annotations

import pymupdf

from layoutkeep.writers.pdf_writer import _line_quads


def test_an_unfindable_line_falls_back_to_its_box() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    box = pymupdf.Rect(20, 20, 200, 40)
    quads = _line_quads(page, "text that is not on this page", box)
    assert len(quads) == 1
    assert quads[0].rect == box
