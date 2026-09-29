"""Figure labels baked into a picture's pixels, read by OCR.

Görselin piksellerine gömülü şekil etiketlerini OCR ile okur.
"""

from __future__ import annotations

import pymupdf
from PIL import Image

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Line,
    Span,
    Style,
)
from layoutkeep.readers._nonprose import is_prose_label
from layoutkeep.readers._pdf_common import _overlap_share

#: Resolution a picture is read at for its labels, and the least OCR confidence a label is taken at.
_RASTER_LABEL_DPI = 200
_RASTER_LABEL_CONFIDENCE = 0.8
_raster_engine = None


def _raster_labels(page: pymupdf.Page, index: int, owner: int, box: BBox, taken: list[BBox]) -> list[Block]:
    """Labels read from a picture's pixels on a born-digital page (translation.figure_text on).

    A diagram in a slide deck or a scanned figure pasted into a PDF has its words in the image, not
    in the text layer, so the text-layer rule never sees them. OCR reads the region; a line that
    reads as words (`is_prose_label`), that OCR is sure of, and that no text-layer block already
    covers becomes a FIGURE_LABEL marked `raster`, which the writer erases from the picture and
    redraws translated. Names and signals stay part of the picture.
    """
    global _raster_engine
    if _raster_engine is None:
        from layoutkeep.ocr.engine import RapidOcrEngine

        _raster_engine = RapidOcrEngine()
    clip = pymupdf.Rect(box.x0, box.y0, box.x1, box.y1)
    if clip.is_empty:
        return []
    pixmap = page.get_pixmap(dpi=_RASTER_LABEL_DPI, clip=clip)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    scale = 72.0 / _RASTER_LABEL_DPI
    labels: list[Block] = []
    for found in _raster_engine.recognize(image):
        text = " ".join(found.text.split())
        if found.confidence < _RASTER_LABEL_CONFIDENCE or not is_prose_label(text):
            continue
        x0, y0, x1, y1 = found.bbox
        bbox = BBox(clip.x0 + x0 * scale, clip.y0 + y0 * scale, clip.x0 + x1 * scale, clip.y0 + y1 * scale)
        if any(_overlap_share(bbox, other) > 0.3 for other in taken):
            continue
        style = Style(size=round((bbox.y1 - bbox.y0) * 0.8, 1))
        labels.append(
            Block(
                id=f"p{index}#r{owner}.{len(labels)}", role=BlockRole.FIGURE_LABEL, bbox=bbox,
                lines=[Line(spans=[Span(text=text, bbox=bbox, style=style)], bbox=bbox)],
                confidence=found.confidence, raster=True,
            )
        )
    return labels
