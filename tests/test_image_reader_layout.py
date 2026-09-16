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
