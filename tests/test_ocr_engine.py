"""Unit tests for ocr.engine.RapidOcrEngine against a fixture image."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_image_fixture import (
    PLAIN_TEXT,
    SPARSE_PAGE_TEXT,
    build_plain_white,
    build_sparse_page,
)
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


def test_recognize_finds_text_on_a_mostly_blank_page(tmp_path: Path) -> None:
    """A DOCX header, footer or footnote becomes its own A4-sized DocIR page
    (`writers/pdf_generator.py`'s flowing-page fallback keeps every page the same sheet size),
    and rasterizing that page to PNG produces something 99%+ blank. RapidOCR's own detector found
    nothing on a real one of these - measured, a 4-page DOCX (body + header + footer + footnotes)
    lost 27% of its words this way on the round trip through PNG. Not because the text was
    unreadable: cropped to a margin around it, the same model read it at 98% confidence.
    `RapidOcrEngine.recognize` now does that cropping itself before handing the page to the
    detector.
    """
    src = tmp_path / "sparse.png"
    build_sparse_page(src)
    image = Image.open(src)

    boxes = RapidOcrEngine().recognize(image)

    assert len(boxes) == 1
    box = boxes[0]
    assert box.text == SPARSE_PAGE_TEXT
    assert box.confidence > 0.9
    # The crop only changes what the detector sees, not the coordinate space it reports in -
    # the box must still land where the text was actually drawn on the full page.
    x0, y0, x1, y1 = box.bbox
    assert 80 <= x0 <= 120
    assert 100 <= y0 <= 140
    assert x1 < 500  # nowhere near the far side of a 1240px-wide page
    assert 0 <= x0 < x1 <= image.width
    assert 0 <= y0 < y1 <= image.height


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
