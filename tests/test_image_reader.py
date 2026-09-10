"""Unit tests for readers.image_reader against the fixture images.

Fixtures are built with known text, at a known position, over a known ground colour - see
`fixtures/build_image_fixture.py` - so OCR output can be checked against exact ground truth
instead of eyeballing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_image_fixture import (
    COLORED_TEXT,
    IMAGE_TEXT,
    LOW_RES_TEXT,
    PLAIN_TEXT,
    SKEW_TEXT,
    build_colored_ground,
    build_low_resolution,
    build_plain_white,
    build_skewed,
    build_text_over_image,
)

from layoutkeep.readers.image_reader import NEEDS_REVIEW_THRESHOLD, is_scanned_page, read_image

_COLOR_TOLERANCE = 30  # per-channel, absorbs anti-aliasing at glyph edges


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def _close(color: str, expected_rgb: tuple[int, int, int]) -> bool:
    got = _hex_to_rgb(color)
    return all(abs(a - b) <= _COLOR_TOLERANCE for a, b in zip(got, expected_rgb, strict=True))


def test_plain_white_ground(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)
    doc = read_image(src)

    assert doc.source_format == "image"
    assert len(doc.pages) == 1
    blocks = doc.pages[0].blocks_in_reading_order()
    assert len(blocks) == 1
    block = blocks[0]
    assert block.text == PLAIN_TEXT
    assert block.order == 0

    style = block.dominant_style()
    assert _close(style.color, (0, 0, 0))
    assert style.background is not None
    assert _close(style.background, (255, 255, 255))

    assert block.confidence > NEEDS_REVIEW_THRESHOLD
    assert block.needs_review is False


def test_colored_ground_detects_both_colors(tmp_path: Path) -> None:
    src = tmp_path / "colored.png"
    build_colored_ground(src)
    doc = read_image(src)

    block = doc.pages[0].blocks_in_reading_order()[0]
    assert block.text == COLORED_TEXT
    style = block.dominant_style()
    assert _close(style.color, (255, 220, 0))  # yellow text
    assert style.background is not None
    assert _close(style.background, (30, 60, 120))  # dark blue ground


def test_text_over_busy_background(tmp_path: Path) -> None:
    src = tmp_path / "over_image.png"
    build_text_over_image(src)
    doc = read_image(src)

    block = doc.pages[0].blocks_in_reading_order()[0]
    assert block.text == IMAGE_TEXT


def test_low_resolution_still_recognized(tmp_path: Path) -> None:
    src = tmp_path / "low_res.png"
    build_low_resolution(src)
    doc = read_image(src)

    block = doc.pages[0].blocks_in_reading_order()[0]
    assert block.text == LOW_RES_TEXT


def test_skewed_text_still_recognized(tmp_path: Path) -> None:
    src = tmp_path / "skewed.png"
    build_skewed(src)
    doc = read_image(src)

    block = doc.pages[0].blocks_in_reading_order()[0]
    assert block.text == SKEW_TEXT


def test_bold_and_italic_are_never_guessed(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)
    doc = read_image(src)
    for line in doc.pages[0].blocks[0].lines:
        for span in line.spans:
            assert span.style.bold is False
            assert span.style.italic is False


def test_is_scanned_page() -> None:
    assert is_scanned_page("") is True
    assert is_scanned_page("   \n  ") is True
    assert is_scanned_page("3") is True  # a lone page number, well under the threshold
    assert is_scanned_page("A" * 50) is False


def _find_numpy_fields(obj: object, path: str = "doc") -> list[str]:
    # DocIR ağacında numpy tipi alan arayan özyinelemeli tarayıcı / Recursively finds numpy types in DocIR tree
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in _find_numpy_fields(v, f"{path}.{k}")]
    if isinstance(obj, list):
        return [x for i, v in enumerate(obj) for x in _find_numpy_fields(v, f"{path}[{i}]")]
    return [path] if type(obj).__module__ == "numpy" else []


def test_no_numpy_types_in_docir(tmp_path: Path) -> None:
    # Görsel okuyucunun DocIR'e numpy tipi sızdırmamasını doğrular / Verifies no numpy types leak into DocIR
    from dataclasses import asdict

    src = tmp_path / "plain.png"
    build_plain_white(src)
    doc = read_image(src)
    found = _find_numpy_fields(asdict(doc))
    assert found == [], f"DocIR'de numpy alanlari bulundu / numpy fields found in DocIR: {found}"


def test_image_save_project_roundtrip(tmp_path: Path) -> None:
    # Görsel kaynakli DocIR'in save_project -> load_project turunun hatasiz çalışmasını doğrular
    from layoutkeep.core.docir import load_project, save_project

    src = tmp_path / "plain.png"
    build_plain_white(src)
    doc = read_image(src)
    proj = tmp_path / "test.lkproj"
    save_project(doc, proj)
    loaded = load_project(proj)
    assert len(loaded.pages) == 1
    assert len(loaded.pages[0].blocks) == len(doc.pages[0].blocks)
    # Metin korunmuş olmalı / Text must survive roundtrip
    assert loaded.pages[0].blocks[0].text == doc.pages[0].blocks[0].text
