"""Text inside an embedded form is not moved by the redaction of text elsewhere on the page.

Think Python page 23: Figure 3.1 is a form XObject. Redacting ANY translated block on the page -
even the running header 150 pt above it - made MuPDF rewrite the page and substitute a new form for
the figure, and in that copy 8 of 11 labels sat up to 11 pt lower: "'Bing tiddle'" over "'tiddle
bang.'", the bottom row clipped. Nothing on the figure was translated or redrawn. After redaction a
rewritten form that holds nothing the redaction had to remove is restored from the original.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.writers.pdf_writer import redact_keeping_forms


def _page_with_form(tmp_path: Path) -> pymupdf.Document:
    figure = pymupdf.open()
    fpage = figure.new_page(width=280, height=140)
    for row, text in enumerate(["'Bing tiddle '", "'tiddle bang.'", "__main__"]):
        fpage.insert_text((20, 30 + row * 14), text, fontsize=10)
    fpath = tmp_path / "figure.pdf"
    figure.save(str(fpath))

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 60), "3.9. Stack diagrams", fontsize=11)
    page.show_pdf_page(pymupdf.Rect(150, 90, 430, 230), pymupdf.open(str(fpath)), 0)
    page.insert_text((72, 300), "Parameters are also local.", fontsize=11)
    return doc


def _spans(page: pymupdf.Page) -> list[tuple[int, str]]:
    return sorted(
        (round(s["bbox"][1]), s["text"])
        for b in page.get_text("dict")["blocks"] if b["type"] == 0
        for line in b["lines"] for s in line["spans"]
    )


def test_redaction_elsewhere_leaves_form_text_where_it_was(tmp_path: Path) -> None:
    doc = _page_with_form(tmp_path)
    page = doc[0]
    before = [s for s in _spans(page) if "tiddle" in s[1] or "__main__" in s[1]]
    redact_keeping_forms(page, [pymupdf.Rect(70, 48, 250, 64), pymupdf.Rect(70, 288, 300, 304)])
    after = _spans(page)
    assert all(s in after for s in before), (before, after)
    assert not any("Stack diagrams" in s[1] or "Parameters" in s[1] for s in after)


def test_text_redacted_inside_a_form_stays_redacted(tmp_path: Path) -> None:
    doc = _page_with_form(tmp_path)
    page = doc[0]
    inside = next(w for w in page.get_text("words") if "__main__" in w[4])
    x0, y0, x1, y1 = inside[:4]
    redact_keeping_forms(page, [pymupdf.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)])
    assert "__main__" not in page.get_text()
