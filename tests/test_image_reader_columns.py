"""A two-column scan reads as two columns, with no layout model installed.

WHAT WAS WRONG. Paragraph grouping ran over the whole page at once. Lines were sorted top to
bottom, which interleaves the columns, and the body column (the median left edge over the page's
long lines) landed in ONE of them. Every line of the other then sat hundreds of points to its
left - the signature of a margin keyword - so each became its own block. Measured on
`tests/fixtures/build_scanned_styles.py`'s two_column page at 200 DPI: 16 blocks, 8 beginning
mid-sentence.

Three per-line rules were tried and each broke a case that already worked (see
`readers/_segment.py`). What fixed it is cutting the page by its own whitespace before grouping:
the gutter is a tall empty band, so each column is grouped on its own. Same page after: 4 blocks,
0 fragments, and the five other styles unchanged.

These go through `_page_from_image`, not the grouping function, because the grouping function
alone still sees whatever lines it is given - the fix is in the order the reader does things.
"""

from __future__ import annotations

from PIL import Image

from layoutkeep.ocr.engine import TextBox
from layoutkeep.readers.image_reader import _page_from_image

_H = 8.0
_LEFT_X, _RIGHT_X = 60.0, 310.0
_COL_W = 210.0


class _Engine:
    def __init__(self, boxes: list[TextBox]) -> None:
        self._boxes = boxes

    def recognize(self, image) -> list[TextBox]:
        return self._boxes


def _box(x0: float, top: float, width: float = _COL_W, text: str = "x") -> TextBox:
    return TextBox(text=text, bbox=(x0, top, x0 + width, top + _H), confidence=0.99)


def _shape(boxes: list[TextBox]) -> list[int]:
    image = Image.new("RGB", (600, 800), "white")
    image.info["dpi"] = (72, 72)
    page = _page_from_image(image, number=1, source_ref="0", engine=_Engine(boxes))
    return [len(block.lines) for block in page.blocks]


def _two_columns(rows: int, top: float = 70.0) -> list[TextBox]:
    boxes: list[TextBox] = []
    for row in range(rows):
        boxes.append(_box(_LEFT_X, top + row * 12.0, text=f"left {row}"))
        boxes.append(_box(_RIGHT_X, top + row * 12.0, text=f"right {row}"))
    return boxes


def test_two_columns_become_two_paragraphs() -> None:
    """Neither column may be mistaken for a margin note beside the other."""
    assert sorted(_shape(_two_columns(5))) == [5, 5]


def test_a_full_width_line_is_not_forced_into_a_column() -> None:
    """A title across both columns belongs to neither, and must not glue them together."""
    title = _box(60.0, 30.0, width=460.0, text="A Heading Across The Page")
    assert sorted(_shape([title, *_two_columns(3, top=70.0)])) == [1, 3, 3]


def test_a_single_column_page_is_unaffected() -> None:
    """The case three per-line attempts broke: a single column must stay one paragraph."""
    boxes = [_box(74.0, 100.0 + i * 10, width=230.0, text=f"line {i}") for i in range(4)]
    assert _shape(boxes) == [4]
