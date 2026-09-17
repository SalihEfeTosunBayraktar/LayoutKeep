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


def test_a_label_column_inside_one_region_is_not_mixed_into_the_entry(tmp_path: Path) -> None:
    """NIST references page: "[SP800-57 part 1]" in a narrow left column beside its entry, both in
    one region the model drew. Sorted by height, the label's two lines were interleaved with the
    entry's ("Recommendation [SP800-57 for Key Management ... part 1] Technology"), and the model
    lost "part 1" from the mixture on every retry. Inside a region the page's whitespace still
    separates the columns, as it does on scanned pages."""
    src = tmp_path / "refs.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    page.insert_text((72, 200), "[SP800-57", fontsize=10)
    page.insert_text((72, 212), "part 1]", fontsize=10)
    for row, text in enumerate(["NIST Special Publication (SP) 800-57 part 1 Revision 4,",
                                "Recommendation for Key Management, Part 1: General,",
                                "National Institute of Standards and Technology."]):
        page.insert_text((200, 200 + row * 12), text, fontsize=10)
    doc.save(str(src))

    detector = _Detector([("text", (65, 188, 540, 240))])
    blocks = read_pdf(src, layout=detector).pages[0].blocks
    entry = next(b for b in blocks if "Recommendation" in b.text)
    assert "[SP800-57" not in entry.text, entry.text
    assert any(b.text.replace("\n", " ").strip() == "[SP800-57 part 1]" for b in blocks), [b.text for b in blocks]


def test_a_one_line_label_beside_its_entry_is_separated_however_narrow_the_gap(tmp_path: Path) -> None:
    """NIST references page after the whitespace cut: one-line labels ("[SP800-39]") still ended up
    inside their entries. The gap between label (x 77-136) and entry (x 154) is 18 pt, just under
    the structural-gap threshold for 16 pt lines. But the label and the entry's first line sit on the
    same row - two lines side by side cannot be one run of text, whatever the gap."""
    src = tmp_path / "refs1.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    page.insert_text((77, 200), "[SP800-39]", fontsize=12)
    for row, text in enumerate(["NIST Special Publication (SP) 800-39, Managing",
                                "Information Security Risk: Organization, Mission,",
                                "and Information System View, National Institute."]):
        page.insert_text((154, 200 + row * 14), text, fontsize=12)
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("list_item", (70, 185, 540, 240))])).pages[0].blocks
    entry = next(b for b in blocks if "Managing" in b.text)
    assert "[SP800-39]" not in entry.text, entry.text


def test_a_superscript_beside_a_word_does_not_split_its_paragraph(tmp_path: Path) -> None:
    """The guard on the side-by-side rule: a footnote mark set as its own small line next to a word
    is not a second column."""
    src = tmp_path / "sup.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    page.insert_text((80, 200), "Information security protects information", fontsize=11)
    page.insert_text((316, 196), "12", fontsize=6)
    for row, text in enumerate(["and systems from unauthorized access, use and", "disclosure of every kind."], start=1):
        page.insert_text((80, 200 + row * 13), text, fontsize=11)
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("text", (70, 185, 540, 240))])).pages[0].blocks
    prose = [b for b in blocks if "Information security" in b.text or "disclosure" in b.text]
    assert len(prose) == 1, [b.text for b in blocks]
