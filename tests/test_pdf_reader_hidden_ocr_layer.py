"""A scan with a hidden OCR text layer is a scan.

Archive.org's "Text PDF" books, and many scanners, put an invisible text layer (render mode 3)
over the page image so the PDF is searchable. The reader saw text and read the page as born
digital; the writer then removed that invisible text and drew the translation - over the scanned
English, which is pixels and was never touched. Two of the campaign's five books are this kind
(136 and 137 of their pages), and so were pages 4-10 of the NASA report.

What decides it is visibility, not the presence of text: when most of a page's text is invisible,
what the reader sees is the image, and the page goes through OCR and the scanned-page writer.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from layoutkeep.readers.pdf_reader import read_pdf
from tests.test_pdf_reader_scanned import FIXTURE_DPI, PAGE_H_PT, PAGE_W_PT, _font

LINES = ("The enable input may be activated with a zero", "or with a one signal level in the circuit.")


def _scan(path: Path, *, hidden_layer: bool) -> None:
    scale = FIXTURE_DPI / 72.0
    image = Image.new("RGB", (int(PAGE_W_PT * scale), int(PAGE_H_PT * scale)), "white")
    draw = ImageDraw.Draw(image)
    font = _font(int(11 * scale))
    # The visible scan and its hidden layer carry the same lines at the same places, as a real
    # searchable scan does - enough of them that text density alone would call the page digital.
    for row, text in enumerate(LINES * 6):
        draw.text((int(30 * scale), int((100 + row * 16) * scale)), text, fill="black", font=font)
    png = path.with_suffix(".png")
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    if hidden_layer:
        for row, text in enumerate(LINES * 6):
            page.insert_text((30, 112 + row * 16), text, fontsize=11, render_mode=3)
    doc.save(str(path))


def test_a_scan_with_an_invisible_text_layer_reads_as_scanned(tmp_path: Path) -> None:
    src = tmp_path / "searchable_scan.pdf"
    _scan(src, hidden_layer=True)
    page = read_pdf(src).pages[0]
    assert page.scanned, "the invisible OCR layer was taken for born-digital text"
    assert any("enable input" in b.text for b in page.blocks)


def test_visible_text_over_a_background_image_is_still_digital(tmp_path: Path) -> None:
    """A designed page with a full-bleed background picture and real text on top is not a scan."""
    src = tmp_path / "designed.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W_PT, height=PAGE_H_PT)
    png = tmp_path / "bg.png"
    Image.new("RGB", (400, 540), (230, 240, 250)).save(png)
    page.insert_image(pymupdf.Rect(0, 0, PAGE_W_PT, PAGE_H_PT), filename=str(png))
    for row, text in enumerate(LINES * 6):
        page.insert_text((30, 112 + row * 16), text, fontsize=11)
    doc.save(str(src))
    assert not read_pdf(src).pages[0].scanned


def test_the_hidden_english_layer_does_not_survive_translation(tmp_path: Path) -> None:
    """Otherwise the output looks Turkish and searches, copies and reads aloud as English."""
    from layoutkeep.core.docir import apply_segments, segments_from_document
    from layoutkeep.writers.pdf_writer import write_pdf

    src = tmp_path / "searchable_scan.pdf"
    _scan(src, hidden_layer=True)
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = "Etkinlestirme girisi sifir veya bir sinyal seviyesiyle etkinlestirilebilir."
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)
    with pymupdf.open(out) as result:
        text = result[0].get_text()
    assert "enable input" not in text, "the invisible English OCR layer is still in the output"
    assert "Etkinlestirme" in text
