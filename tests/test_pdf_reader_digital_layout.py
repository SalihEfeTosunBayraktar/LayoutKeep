"""Born-digital pages read with the layout model: regions from the model, text from the PDF.

Campaign, NIST SP 800-12 page 6: a table of contents came out with its entries run together
("... 16 3.13 Sistem ...") - the digital reader's rules merged the entry lines into paragraphs,
and the translation reflowed them. The layout model labels that page `document_index` (measured
on pages 6 and 7), and a table of contents is one entry per line. The glyphs and fonts still come
from the PDF, so nothing is re-recognised.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import BlockRole
from layoutkeep.ocr.layout_detector import LayoutRegion
from layoutkeep.readers.pdf_reader import read_pdf

_W, _H = 612.0, 792.0


class _Detector:
    """Answers in the pixels of the image it is shown, as the real model does."""

    def __init__(self, regions_pt: list[tuple[str, tuple[float, float, float, float]]]) -> None:
        self.regions_pt = regions_pt
        self.seen: list[tuple[int, int]] = []

    def detect(self, image):
        self.seen.append(image.size)
        sx, sy = image.width / _W, image.height / _H
        return [
            LayoutRegion(label, (x0 * sx, y0 * sy, x1 * sx, y1 * sy), 0.95)
            for label, (x0, y0, x1, y1) in self.regions_pt
        ]


def _toc(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    entries = ["3.12 Information Security Architect ........ 16", "3.13 System Security Engineer ........ 17",
               "3.14 Security Control Assessor ........ 17", "3.15 System Administrator ........ 17"]
    for row, text in enumerate(entries):
        page.insert_text((80, 100 + row * 14), text, fontsize=11)
    page.insert_text((80, 300), "Information security is the protection of information and", fontsize=11)
    page.insert_text((80, 314), "information systems from unauthorized access and disclosure.", fontsize=11)
    doc.save(str(path))


def test_a_table_of_contents_is_one_block_per_entry(tmp_path: Path) -> None:
    src = tmp_path / "toc.pdf"
    _toc(src)
    detector = _Detector([("document_index", (70, 85, 540, 150)), ("text", (70, 285, 540, 320))])
    page = read_pdf(src, layout=detector).pages[0]
    entries = [b for b in page.blocks if b.bbox.y0 < 160]
    assert len(entries) == 4, [b.text for b in entries]
    assert detector.seen, "the model was not consulted on a digital page"


def test_a_paragraph_region_is_one_block_with_the_models_role(tmp_path: Path) -> None:
    src = tmp_path / "toc.pdf"
    _toc(src)
    detector = _Detector([("document_index", (70, 85, 540, 150)), ("section_header", (70, 285, 540, 320))])
    page = read_pdf(src, layout=detector).pages[0]
    body = [b for b in page.blocks if b.bbox.y0 > 280]
    assert len(body) == 1 and body[0].role == BlockRole.HEADING, [(b.role, b.text) for b in body]


def test_lines_outside_every_region_are_still_read(tmp_path: Path) -> None:
    src = tmp_path / "toc.pdf"
    _toc(src)
    page = read_pdf(src, layout=_Detector([("document_index", (70, 85, 540, 150))])).pages[0]
    assert any("unauthorized access" in b.text for b in page.blocks)


def test_without_a_model_digital_reading_is_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "toc.pdf"
    _toc(src)
    with_none = [b.text for b in read_pdf(src).pages[0].blocks]
    assert any("3.12" in t for t in with_none)
