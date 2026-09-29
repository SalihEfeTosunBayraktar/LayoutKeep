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

    def __init__(
        self,
        regions_pt: list[tuple[str, tuple[float, float, float, float]]],
        size: tuple[float, float] = (_W, _H),
    ) -> None:
        self.regions_pt = regions_pt
        self.size = size  # the page the recorded regions were measured on, in points
        self.seen: list[tuple[int, int]] = []

    def detect(self, image):
        self.seen.append(image.size)
        width, height = self.size
        sx, sy = image.width / width, image.height / height
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


def test_a_justified_line_split_at_a_wide_space_stays_in_its_paragraph(tmp_path: Path) -> None:
    """Think Python p. 139: a justified line came out of the PDF as two lines - a URL fragment in the
    code font, a stretched space, then prose - and the side-by-side rule cut the paragraph there.
    The URL's other lines became a block of their own and the paragraph lost them. A paragraph's
    other lines run across that gap; two real columns leave it empty."""
    src = tmp_path / "justified.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    page.insert_text((130, 210), "For more information on the format operator, see https://docs.org/3/", fontsize=10)
    page.insert_text((130, 222), "stdtypes.html#printf-style-formatting.", fontsize=10, fontname="cour")
    page.insert_text((377, 222), "A more powerful alternative is", fontsize=10)
    page.insert_text((130, 234), "the string format method, which you can read about at https://docs.org/", fontsize=10)
    page.insert_text((130, 246), "library/stdtypes.html#str.format.", fontsize=10, fontname="cour")
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("text", (120, 195, 540, 252))])).pages[0].blocks
    prose = [b for b in blocks if "stdtypes" in b.text or "information" in b.text]
    assert len(prose) == 1, [b.text for b in blocks]


def test_two_index_columns_are_split_at_their_gutter_not_halfway_between_two_entries(tmp_path: Path) -> None:
    """Think Python's index: a short entry ("suffix, 131") beside the right column's entry. Halfway
    between the two lies inside the left column, where a longer entry runs; the columns are still
    two, cut at the gutter no line crosses."""
    src = tmp_path / "index.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    left = ["suffix, 131", "superstitious debugging of loops, 200", "syntax error, 14"]
    right = ["Turing Thesis, 55", "tuple assignment, 138", "type checking, 84"]
    for row, (a, b) in enumerate(zip(left, right, strict=True)):
        page.insert_text((130, 200 + row * 13), a, fontsize=10)
        page.insert_text((340, 200 + row * 13), b, fontsize=10)
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("text", (120, 185, 540, 240))])).pages[0].blocks
    assert not any("suffix" in b.text and "Turing" in b.text for b in blocks), [b.text for b in blocks]


def test_text_inside_a_picture_is_kept_as_it_is_on_a_digital_page_too(tmp_path: Path) -> None:
    """Think Python page 97: a stack diagram's labels are PDF text. Translated line by line they
    became "harfler" for the variable "letters", "basligi sil" for the function "delete_head", "'k'"
    for the value "'c'", and "t" and "__main__" disappeared - the diagram no longer said what the
    code does. Scanned pages already keep a picture's text as it is; digital pages now do too."""
    from layoutkeep.core.docir import NON_TRANSLATABLE_ROLES

    src = tmp_path / "diagram.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    for x, y, text in ((150, 110, "__main__"), (230, 110, "letters"), (140, 140, "delete_head"), (300, 110, "list")):
        page.insert_text((x, y), text, fontsize=10)
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("picture", (120, 90, 420, 160))])).pages[0].blocks
    assert blocks and all(b.role in NON_TRANSLATABLE_ROLES for b in blocks), [(b.role, b.text) for b in blocks]


def test_paragraphs_inside_one_text_region_are_split_at_their_blank_line(tmp_path: Path) -> None:
    """Held-out Wikipedia "Printing press", page 9: the model boxed the whole page as one text region,
    and its four paragraphs came out as one 4,000-character block the model never answered - the page
    was lost. The paragraphs are separated by a blank line: 15 pt between them against 2.5-3 pt
    between lines, which is still under the whitespace cut's 1.2 line heights (15.9 pt)."""
    src = tmp_path / "paragraphs.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=_W, height=_H)
    first = ["Printing presses spread quickly across Europe during the late fifteenth century,",
             "and within a few decades most large cities had at least one workshop producing",
             "books, pamphlets and broadsheets for a growing number of readers in many towns."]
    second = ["Quantitative work in economics has tested some of these claims about growth,",
              "finding that cities where printing was established grew faster than comparable",
              "cities without presses between the years fifteen hundred and sixteen hundred."]
    top = 120.0
    for text in first:
        page.insert_text((72, top), text, fontsize=11)
        top += 14.5
    top += 13.0  # a blank line between the paragraphs
    for text in second:
        page.insert_text((72, top), text, fontsize=11)
        top += 14.5
    doc.save(str(src))

    blocks = read_pdf(src, layout=_Detector([("text", (60, 100, 560, top))])).pages[0].blocks
    prose = [b.text for b in blocks if "Printing presses" in b.text or "Quantitative" in b.text]
    assert len(prose) == 2, prose


#: Page 2 of the Turkish Penal Code source the campaign measured (see CREDITS.md), kept as a
#: fixture. Its page is bigger than the synthetic ones above, so the recorder's size is passed
#: along with the regions it measured.
_TCK_P2_SIZE = (595.32, 841.92)

#: The regions the REAL layout model returned for that page, recorded once by rendering it at
#: 100 DPI (`pdf_reader._DIGITAL_LAYOUT_DPI`) and running `layout_detector.load_detector()` on the
#: pixels, `resolve_duplicates` included, then scaled back to page points. Recorded rather than
#: re-run so the test needs no installed model (conftest switches the model off).
_TCK_P2_REGIONS = [
    ("section_header", (286.0, 72.4, 308.2, 81.2)),
    ("text", (97.2, 97.3, 328.3, 106.2)),
    ("text", (70.3, 145.0, 524.1, 166.2)),
    ("text", (97.3, 169.4, 308.6, 178.2)),
    ("text", (70.1, 181.1, 524.2, 213.7)),
    ("text", (97.2, 217.6, 187.5, 226.6)),
    ("text", (70.1, 228.6, 524.1, 262.8)),
    ("section_header", (97.3, 275.4, 142.6, 284.3)),
    ("text", (70.1, 277.4, 524.4, 322.1)),
    ("list_item", (70.1, 348.7, 524.2, 370.3)),
    ("text", (97.2, 373.1, 251.5, 382.1)),
    ("text", (70.0, 384.8, 524.2, 406.7)),
    ("text", (258.7, 419.9, 337.0, 441.7)),
    ("section_header", (97.5, 444.6, 199.0, 453.0)),
    ("text", (70.3, 456.5, 524.0, 478.1)),
]


def test_the_leftovers_of_one_block_are_split_where_the_model_claimed_lines() -> None:
    """Turkish Penal Code page 2, a Word-generated PDF: ONE pymupdf block held 43 lines, the whole
    page's articles, and the model claimed 15 stretches of it. The lines it did not claim were put
    into a single block whose box was their union - y 83..418, 335 pt tall - so 'Madde 175' (a
    heading at y 130), 'Trafik güvenliğini tehlikeye sokma' (y 334) and '(2) Kara, deniz...'
    (y 324-346) were one block: the translation was drawn squeezed into a thin strip at the top of
    the page and the places those lines came from were left blank. Unclaimed lines now form a block
    per run of consecutive ones, and a claimed line between two runs ends the run.
    """
    src = Path(__file__).parent / "fixtures" / "pdf_tck_5237_p2.pdf"
    page = read_pdf(src, layout=_Detector(_TCK_P2_REGIONS, _TCK_P2_SIZE)).pages[0]

    tallest = max(page.blocks, key=lambda b: b.bbox.height)
    assert tallest.bbox.height < 120, (tallest.id, tallest.bbox, tallest.text[:80])

    madde = next(b for b in page.blocks if "Madde 175" in b.text)
    kara = next(b for b in page.blocks if "(2) Kara" in b.text)
    assert madde.id != kara.id, (madde.id, madde.text)
    assert madde.bbox.y1 < kara.bbox.y0, (madde.bbox, kara.bbox)


def test_a_whitespace_line_does_not_stretch_a_leftover_block_over_a_heading() -> None:
    """Same page, bench arm d-tr: the 'Madde 175' block's box began at y 96, the heading's own row -
    a line holding nothing but spaces sat there and joined the run. The heading's translation was
    then drawn inside the article's box and the two overlapped (L7, 7 word pairs). A line with no
    text is no part of a paragraph, and no block of spaces is read at all.
    """
    src = Path(__file__).parent / "fixtures" / "pdf_tck_5237_p2.pdf"
    page = read_pdf(src, layout=_Detector(_TCK_P2_REGIONS, _TCK_P2_SIZE)).pages[0]

    assert all(b.text.strip() for b in page.blocks), [b.id for b in page.blocks if not b.text.strip()]
    madde = next(b for b in page.blocks if "Madde 175" in b.text)
    heading = next(b for b in page.blocks if b.text.strip().startswith("Akıl hastası") and b.id != madde.id)
    assert madde.bbox.y0 >= heading.bbox.y1 - 1, (madde.bbox, heading.bbox)
