"""Reading a scanned page with a layout detector, without the model file.

The detector and the recogniser are both stand-ins, so what is tested is what the reader does
with regions, not whether the model finds them - that is measured on real pages in
`tests/layout_eval/`. Each case is one seen in the model's raw output there.
"""

from __future__ import annotations

from PIL import Image

from layoutkeep.core.docir import BlockRole
from layoutkeep.ocr.engine import TextBox
from layoutkeep.ocr.layout_detector import LayoutRegion
from layoutkeep.readers.image_reader import _page_from_image

_H = 20.0


class _Engine:
    def __init__(self, boxes: list[TextBox]) -> None:
        self._boxes = boxes

    def recognize(self, image) -> list[TextBox]:
        return self._boxes


class _Detector:
    def __init__(self, regions: list[LayoutRegion]) -> None:
        self._regions = regions

    def detect(self, image) -> list[LayoutRegion]:
        return self._regions


def _box(text: str, x0: float, top: float, width: float, height: float = _H) -> TextBox:
    return TextBox(text=text, bbox=(x0, top, x0 + width, top + height), confidence=0.99)


def _read(boxes: list[TextBox], regions: list[LayoutRegion]):
    image = Image.new("RGB", (1000, 1400), "white")
    image.info["dpi"] = (200, 200)
    return _page_from_image(
        image, number=1, source_ref="0", engine=_Engine(boxes), layout=_Detector(regions)
    )


def _paragraph(x0: float, top: float, rows: int, word: str = "text") -> list[TextBox]:
    return [_box(f"{word} {i}", x0, top + i * 30, 600) for i in range(rows)]


def test_a_text_region_becomes_one_block_with_the_models_role() -> None:
    boxes = [_box("Decoder Expansion", 100, 100, 200), *_paragraph(100, 140, 4)]
    regions = [
        LayoutRegion("section_header", (95, 95, 305, 125), 0.95),
        LayoutRegion("text", (95, 135, 705, 255), 0.98),
    ]
    page = _read(boxes, regions)
    assert [(b.role, len(b.lines)) for b in page.blocks] == [
        (BlockRole.HEADING, 1),
        (BlockRole.BODY, 4),
    ]


def test_an_equation_is_a_formula_and_not_larger_than_the_body() -> None:
    """Book page 54: a tall sigma made the box tall, and the box height made the size."""
    boxes = [*_paragraph(100, 100, 3), _box("F(A, B) = SUM (0, 2)", 300, 220, 300, height=40)]
    regions = [
        LayoutRegion("text", (95, 95, 705, 185), 0.97),
        LayoutRegion("formula", (295, 215, 605, 265), 0.94),
    ]
    page = _read(boxes, regions)
    body, formula = page.blocks
    assert formula.role == BlockRole.FORMULA
    assert formula.dominant_style().size <= body.dominant_style().size


def test_a_margin_note_boxed_with_the_body_is_still_its_own_block() -> None:
    """The small_trim fixture at 200 DPI: one box over the keyword and the paragraph."""
    boxes = [_box("decoder", 10, 100, 80), *_paragraph(300, 100, 4)]
    page = _read(boxes, [LayoutRegion("text", (5, 95, 905, 215), 0.96)])
    texts = sorted(b.text for b in page.blocks)
    assert "decoder" in texts, texts
    assert all("decoder" not in t for t in texts if t != "decoder")


def test_a_loose_box_does_not_merge_paragraphs_it_surrounds() -> None:
    boxes = [*_paragraph(100, 100, 2, "first"), *_paragraph(100, 300, 2, "second")]
    regions = [
        LayoutRegion("text", (95, 95, 705, 155), 0.8),
        LayoutRegion("text", (95, 295, 705, 355), 0.8),
        LayoutRegion("text", (90, 90, 710, 360), 0.66),
        LayoutRegion("list_item", (95, 290, 705, 360), 0.5),
    ]
    page = _read(boxes, regions)
    assert len(page.blocks) == 2


def test_two_columns_read_left_column_first() -> None:
    boxes = [*_paragraph(50, 100, 5, "left"), *_paragraph(700, 100, 5, "right")]
    boxes = [TextBox(b.text, (b.bbox[0], b.bbox[1], b.bbox[0] + 250, b.bbox[3]), 0.99) for b in boxes]
    regions = [
        LayoutRegion("text", (695, 95, 955, 245), 0.95),
        LayoutRegion("text", (45, 95, 305, 245), 0.95),
    ]
    page = _read(boxes, regions)
    assert [b.text.split()[0] for b in page.blocks] == ["left", "right"]


def test_lines_the_model_missed_are_still_read() -> None:
    boxes = [*_paragraph(100, 100, 3), _box("orphan line", 100, 600, 200)]
    page = _read(boxes, [LayoutRegion("text", (95, 95, 705, 185), 0.97)])
    assert any("orphan line" in b.text for b in page.blocks)


def test_no_detector_reads_as_before() -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    image.info["dpi"] = (200, 200)
    boxes = _paragraph(100, 100, 3)
    page = _page_from_image(image, number=1, source_ref="0", engine=_Engine(boxes))
    assert len(page.blocks) == 1


def test_the_same_line_under_two_labels_takes_the_surer_label() -> None:
    """NASA report symbol list: an entry boxed as `text` 0.56 and `list_item` 0.71.

    The `text` box is the tighter of the two, so without resolving duplicates the smaller-box
    rule would pick the less certain label.
    """
    boxes = [_box("drag, lb", 100, 100, 200)]
    regions = [
        LayoutRegion("text", (98, 98, 302, 122), 0.56),
        LayoutRegion("list_item", (96, 96, 304, 124), 0.71),
    ]
    assert [b.role for b in _read(boxes, regions).blocks] == [BlockRole.LIST]


def test_table_cells_stay_separate_blocks() -> None:
    """Book page 451: a function table's column came back merged into one block."""
    boxes = [*_paragraph(100, 100, 3)]
    boxes += [_box(text, 600, 400 + i * 22, 150) for i, text in enumerate(
        ["High-impedance", "High-impedance", "Input data to RAM", "Output data from RAM"])]
    regions = [
        LayoutRegion("text", (95, 95, 705, 185), 0.97),
        LayoutRegion("table", (90, 390, 800, 500), 0.9),
    ]
    page = _read(boxes, regions)
    cells = [b.text for b in page.blocks if b.bbox.y0 >= 390]
    assert cells == ["High-impedance", "High-impedance", "Input data to RAM", "Output data from RAM"]


def test_the_ceiling_does_not_shrink_ordinary_body_text() -> None:
    """Book page 451: capping at the median WORD box cut ordinary paragraphs down.

    One paragraph of many short word boxes in a smaller size outnumbers the boxes of two
    ordinary paragraphs, so the median over word boxes is the small size. Measured per block,
    two of three paragraphs are the ordinary size, and that is the body.
    """
    dense = [_box(f"s{i}", 100 + i * 60, 100 + (i // 9) * 30, 50, height=18) for i in range(9)]
    first = [_box(f"a{i}", 100 + i * 200, 300, 180, height=22) for i in range(3)]
    second = [_box(f"b{i}", 100 + i * 200, 500, 180, height=22) for i in range(3)]
    regions = [
        LayoutRegion("text", (95, 95, 705, 125), 0.97),
        LayoutRegion("text", (95, 295, 705, 325), 0.97),
        LayoutRegion("text", (95, 495, 705, 525), 0.97),
    ]
    page = _read([*dense, *first, *second], regions)
    sizes = [b.dominant_style().size for b in page.blocks]
    assert sizes[1] == sizes[2] > sizes[0], sizes


def test_table_cells_do_not_pull_the_body_size_down() -> None:
    """Book page 451 after the first ceiling fix: still 6.03pt against a 6.60pt body.

    Table cells and figure labels are blocks too, in small type, and there are many of them.
    Counted as running text they outvote the paragraphs; only text regions measure the body.
    """
    paragraph = [_box(f"p{i}", 100, 100 + i * 30, 600, height=22) for i in range(2)]
    cells = [_box(f"c{i}", 100 + (i % 3) * 200, 400 + (i // 3) * 22, 150, height=16) for i in range(9)]
    regions = [
        LayoutRegion("text", (95, 95, 705, 155), 0.97),
        LayoutRegion("table", (90, 390, 800, 480), 0.9),
    ]
    page = _read([*paragraph, *cells], regions)
    body = next(b for b in page.blocks if b.text.startswith("p0"))
    reference = _read(paragraph, regions[:1]).blocks[0]
    assert body.dominant_style().size == reference.dominant_style().size


def test_text_inside_a_picture_stays_as_scanned() -> None:
    """Book page 61, round 3: labels inside a circuit diagram ("2 x 4 decoder", "D2") were each
    made a block, translated and re-typeset over the drawing - "kod cozucu" squeezed between the
    wires, subscripts redrawn as "D{2}". A picture's text is part of the picture."""
    from layoutkeep.core.docir import NON_TRANSLATABLE_ROLES

    boxes = [*_paragraph(100, 100, 2), _box("2 x 4 decoder", 300, 400, 90), _box("D2", 500, 420, 20)]
    regions = [
        LayoutRegion("text", (95, 95, 705, 155), 0.97),
        LayoutRegion("picture", (250, 380, 600, 600), 0.97),
    ]
    page = _read(boxes, regions)
    labels = [b for b in page.blocks if b.bbox.y0 >= 380]
    assert labels and all(b.role in NON_TRANSLATABLE_ROLES for b in labels), [b.role for b in labels]


def test_table_cells_are_still_translated() -> None:
    from layoutkeep.core.docir import NON_TRANSLATABLE_ROLES

    boxes = [_box("Output data from RAM", 600, 400, 150)]
    page = _read(boxes, [LayoutRegion("table", (90, 390, 800, 500), 0.9)])
    assert page.blocks[0].role not in NON_TRANSLATABLE_ROLES


def test_separate_boxes_on_one_line_keep_a_space_between_them() -> None:
    """Every translated running header came out as "46BOLUM IKI ...": OCR returns the folio and
    the header as two boxes on one line, and a line's text is its spans joined with nothing - right
    for a PDF text layer, whose spans carry their own spaces, wrong for OCR boxes, whose gap is
    only visual."""
    boxes = [_box("46", 20, 30, 20), _box("CHAPTER TWO Digital Components", 70, 30, 300)]
    page = _read(boxes, [LayoutRegion("page_header", (15, 25, 380, 55), 0.94)])
    assert page.blocks[0].text == "46 CHAPTER TWO Digital Components"


def test_words_of_two_columns_are_never_joined_into_one_line() -> None:
    """Popular Science, January 1920: on a page with a narrow gutter, words of both columns at the
    same height were joined into one line ("ers. Ancak bu seyler ..." spanning x=33-570), so the
    translation mixed two paragraphs and was drawn over both columns. The model's regions are the
    columns; boxes are grouped by region before they are joined into lines."""
    left = [_box(f"left{i}", 40 + i * 70, 300, 60) for i in range(4)]     # x 40..310
    right = [_box(f"right{i}", 330 + i * 70, 300, 60) for i in range(4)]  # x 330..600, gutter 20px
    regions = [
        LayoutRegion("text", (35, 290, 315, 330), 0.95),
        LayoutRegion("text", (325, 290, 605, 330), 0.95),
    ]
    page = _read([*left, *right], regions)
    texts = sorted(b.text for b in page.blocks)
    assert texts == ["left0 left1 left2 left3", "right0 right1 right2 right3"], texts
