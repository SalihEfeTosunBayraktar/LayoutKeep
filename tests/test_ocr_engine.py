"""Unit tests for ocr.engine.RapidOcrEngine against a fixture image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_image_fixture import PLAIN_TEXT, build_plain_white
from PIL import Image

from layoutkeep.ocr.engine import RapidOcrEngine, TextBox


def test_recognize_returns_text_bbox_and_confidence(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)
    image = Image.open(src)

    boxes = RapidOcrEngine().recognize(image)

    assert len(boxes) == 1
    box = boxes[0]
    assert isinstance(box, TextBox)
    assert box.text == PLAIN_TEXT
    assert 0.0 <= box.confidence <= 1.0
    assert box.confidence > 0.9  # clean synthetic text, should be near-certain
    x0, y0, x1, y1 = box.bbox
    assert 0 <= x0 < x1 <= image.width
    assert 0 <= y0 < y1 <= image.height


def test_recognize_on_blank_image_returns_no_boxes() -> None:
    blank = Image.new("RGB", (200, 100), "white")
    boxes = RapidOcrEngine().recognize(blank)
    assert boxes == []


def test_engine_construction_is_lazy() -> None:
    # Constructing the engine must not itself trigger a model load/download.
    engine = RapidOcrEngine()
    assert engine._ocr is None


def test_recognize_accepts_str_path(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)

    boxes = RapidOcrEngine().recognize(str(src))

    assert len(boxes) == 1
    assert boxes[0].text == PLAIN_TEXT


def test_recognize_accepts_path_object(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)

    boxes = RapidOcrEngine().recognize(src)

    assert len(boxes) == 1
    assert boxes[0].text == PLAIN_TEXT


def test_recognize_accepts_raw_bytes(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)

    boxes = RapidOcrEngine().recognize(src.read_bytes())

    assert len(boxes) == 1
    assert boxes[0].text == PLAIN_TEXT


def test_recognize_accepts_pil_image(tmp_path: Path) -> None:
    src = tmp_path / "plain.png"
    build_plain_white(src)

    boxes = RapidOcrEngine().recognize(Image.open(src))

    assert len(boxes) == 1
    assert boxes[0].text == PLAIN_TEXT
