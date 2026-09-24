"""A label baked into a picture's pixels, read by OCR and translated (translation.figure_text).

Slide decks and pasted diagrams carry their words in the image, where the text-layer rule cannot
see them. With the setting on, a picture region is read by OCR; a label that reads as words is
erased from the picture and drawn translated, and a signal name stays in the picture.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont
from test_pdf_reader_digital_layout import _Detector

from layoutkeep.core import tunables
from layoutkeep.core.docir import BlockRole, apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf

FONT = Path(__file__).resolve().parents[1] / "src/layoutkeep/assets/fonts/Carlito-Regular.ttf"


def _source(path: Path) -> Path:
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), 44)
    draw.text((40, 40), "Instruction stream byte queue", fill="black", font=font)
    draw.text((40, 180), "ALE", fill="black", font=font)
    draw.rectangle((20, 20, 880, 280), outline="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(pymupdf.Rect(100, 100, 400, 200), stream=buffer.getvalue())
    # Enough running text that the page is born digital, not a scan (the scan path has its own rule).
    for row in range(30):
        page.insert_text((60, 250 + row * 16), "A figure with its words in the pixels, and a page of text around it.", fontsize=11)
    doc.save(str(path))
    return path


@pytest.fixture
def figure_text():
    tunables.set_value("translation.figure_text", True)
    yield
    tunables.set_value("translation.figure_text", False)


def _labels(src: Path):
    page = read_pdf(src, layout=_Detector([("picture", (95, 95, 405, 205)), ("text", (55, 235, 560, 740))])).pages[0]
    return [b for b in page.blocks if b.role is BlockRole.FIGURE_LABEL]


def test_a_prose_label_in_the_pixels_is_read_and_a_signal_name_is_not(tmp_path: Path, figure_text) -> None:
    labels = _labels(_source(tmp_path / "src.pdf"))
    assert len(labels) == 1 and labels[0].raster, [b.text for b in labels]
    assert "Instruction" in labels[0].text


def test_off_by_default_nothing_is_read_from_the_pixels(tmp_path: Path) -> None:
    assert _labels(_source(tmp_path / "src.pdf")) == []


def test_the_label_is_erased_from_the_picture_and_drawn_translated(tmp_path: Path, figure_text) -> None:
    src = _source(tmp_path / "src.pdf")
    doc = read_pdf(src, layout=_Detector([("picture", (95, 95, 405, 205)), ("text", (55, 235, 560, 740))]))
    segments = segments_from_document(doc)
    for segment in segments:
        segment.target = "Komut akışı bayt kuyruğu" if "Instruction" in segment.source else segment.source
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)
    with pymupdf.open(out) as written:
        page = written[0]
        assert "Komut akışı bayt kuyruğu" in page.get_text()
        pixels = page.get_pixmap(dpi=100, clip=pymupdf.Rect(100, 100, 400, 200))
    from layoutkeep.ocr.engine import RapidOcrEngine

    image = Image.frombytes("RGB", (pixels.width, pixels.height), pixels.samples)
    seen = " ".join(box.text for box in RapidOcrEngine().recognize(image))
    assert "Instruction" not in seen and "ALE" in seen, seen
