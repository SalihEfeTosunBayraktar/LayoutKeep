"""Resolving the layout model's duplicate boxes - the cases seen in its raw output."""

from __future__ import annotations

from layoutkeep.ocr.layout_detector import LayoutRegion, resolve_duplicates


def _r(label: str, box: tuple[float, float, float, float], score: float = 0.9) -> LayoutRegion:
    return LayoutRegion(label, box, score)


def test_a_loose_box_around_several_paragraphs_is_dropped() -> None:
    paragraphs = [_r("text", (70, 70 + i * 80, 520, 130 + i * 80), 0.8) for i in range(3)]
    union = _r("text", (69, 68, 523, 290), 0.66)
    kept = resolve_duplicates([union, *paragraphs])
    assert sorted(r.bbox for r in kept) == sorted(r.bbox for r in paragraphs)


def test_the_same_line_under_two_labels_keeps_the_surer_one() -> None:
    kept = resolve_duplicates(
        [_r("text", (770, 895, 930, 915), 0.56), _r("list_item", (771, 894, 931, 916), 0.71)]
    )
    assert [r.label for r in kept] == ["list_item"]


def test_a_heading_touching_its_paragraph_is_not_a_duplicate() -> None:
    heading = _r("section_header", (103, 116, 191, 128), 0.95)
    body = _r("text", (103, 126, 426, 173), 0.94)
    assert len(resolve_duplicates([heading, body])) == 2


def test_text_inside_a_picture_is_hierarchy_and_both_stay() -> None:
    picture = _r("picture", (140, 357, 316, 530), 0.97)
    label = _r("text", (150, 400, 180, 410), 0.6)
    assert len(resolve_duplicates([picture, label])) == 2


def test_one_paragraph_inside_one_larger_box_keeps_the_surer() -> None:
    """Only one child means it is not a union; they are the same text, so score decides."""
    outer = _r("text", (100, 100, 400, 200), 0.9)
    inner = _r("text", (102, 102, 398, 198), 0.7)
    assert resolve_duplicates([outer, inner]) == [outer]
