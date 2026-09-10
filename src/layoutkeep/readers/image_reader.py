"""Image reader: turns a scanned page (a raster image) into a DocIR Document via OCR.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-ocr.md):
  - `ocr.engine.OcrEngine` finds text boxes with a real per-box confidence.
  - Boxes are merged into lines (already mostly true of rapidocr's own detections, but boxes
    split by a mid-line obstruction are re-joined here), then lines into paragraphs by vertical
    gap and left-alignment, mirroring the paragraph grouping `pdf_reader.py` gets for free from
    pymupdf.
  - Reading order is simple top-to-bottom, left-to-right: scanned pages in this phase are not
    given multi-column layout detection (unlike `pdf_reader.py`) because nothing in the Phase 2
    scope calls for it yet; `Block.order` is still filled for real, just via a simpler rule.
  - Text/background colour per block comes from a 2-means split of the block's own pixels.
  - Bold/italic detection is deliberately not attempted (see lk-ocr.md): a wrong guess is worse
    than no guess, so `Style.bold`/`Style.italic` stay at their DocIR defaults (False).

This module must not `import pymupdf` (CONTRACT.md S4 reserves that to the two PDF modules).
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
from PIL import Image

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Direction,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.ocr.engine import OcrEngine, RapidOcrEngine, TextBox

#: Below this OCR confidence, the containing block is flagged for human review.
NEEDS_REVIEW_THRESHOLD = 0.80
#: Assumed image resolution when the file carries no DPI metadata (PIL default for PNG/JPEG
#: created by screenshot/scan tools without an explicit resolution tag).
_DEFAULT_DPI = 96.0
#: A page whose extracted text is shorter than this is treated as scanned/image-only.
_SCANNED_TEXT_CHAR_THRESHOLD = 10


def is_scanned_page(extracted_text: str) -> bool:
    """True when a PDF page's own text layer is negligible, i.e. it is image-only and should be
    handed off to OCR instead. Takes plain text (e.g. pymupdf `Page.get_text()`) rather than a
    pymupdf object so this module stays free of a pymupdf import."""
    return len(extracted_text.strip()) < _SCANNED_TEXT_CHAR_THRESHOLD


def read_image(path: str | Path, *, engine: OcrEngine | None = None) -> Document:
    """Read a single image file into a one-page DocIR Document."""
    image = Image.open(path).convert("RGB")
    page = _page_from_image(image, number=1, source_ref=str(path), engine=engine)
    doc = Document(source_path=str(path), source_format="image")
    doc.pages = [page]
    return doc


def _page_from_image(
    image: Image.Image, *, number: int, source_ref: str, engine: OcrEngine | None = None
) -> Page:
    engine_ = engine if engine is not None else RapidOcrEngine()
    boxes = engine_.recognize(image)
    dpi = float(image.info.get("dpi", (_DEFAULT_DPI, _DEFAULT_DPI))[0]) or _DEFAULT_DPI

    pixels = np.array(image)
    lines = _merge_boxes_into_lines(boxes)
    paragraphs = _merge_lines_into_paragraphs(lines)

    blocks: list[Block] = []
    for i, para in enumerate(paragraphs):
        block = _block_from_paragraph(para, pixels, dpi, index=i, page_index=number - 1)
        block.order = i
        blocks.append(block)

    return Page(
        number=number,
        width=float(image.width),
        height=float(image.height),
        blocks=blocks,
        source_ref=source_ref,
    )


# --------------------------------------------------------------------------------------
# Boxes -> lines -> paragraphs
# --------------------------------------------------------------------------------------


def _merge_boxes_into_lines(boxes: list[TextBox]) -> list[list[TextBox]]:
    """Group boxes whose vertical spans overlap into one line, left-to-right.

    rapidocr already detects whole text lines, so most groups end up with a single box; this
    only kicks in when a line got split into two boxes (e.g. an obstruction mid-line).
    """
    remaining = sorted(boxes, key=lambda b: b.bbox[1])
    lines: list[list[TextBox]] = []
    for box in remaining:
        y0, y1 = box.bbox[1], box.bbox[3]
        mid = (y0 + y1) / 2
        placed = False
        for line in lines:
            line_y0 = min(b.bbox[1] for b in line)
            line_y1 = max(b.bbox[3] for b in line)
            if line_y0 <= mid <= line_y1:
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])
    for line in lines:
        line.sort(key=lambda b: b.bbox[0])
    lines.sort(key=lambda line: min(b.bbox[1] for b in line))
    return lines


def _merge_lines_into_paragraphs(lines: list[list[TextBox]]) -> list[list[list[TextBox]]]:
    """Group consecutive lines into paragraphs by vertical gap and left-alignment."""
    if not lines:
        return []
    paragraphs: list[list[list[TextBox]]] = [[lines[0]]]
    for prev, cur in pairwise(lines):
        prev_bottom = max(b.bbox[3] for b in prev)
        prev_height = prev_bottom - min(b.bbox[1] for b in prev)
        cur_top = min(b.bbox[1] for b in cur)
        gap = cur_top - prev_bottom
        prev_x0 = min(b.bbox[0] for b in prev)
        cur_x0 = min(b.bbox[0] for b in cur)
        same_paragraph = gap <= prev_height * 0.6 and abs(cur_x0 - prev_x0) <= prev_height * 1.5
        if same_paragraph:
            paragraphs[-1].append(cur)
        else:
            paragraphs.append([cur])
    return paragraphs


# --------------------------------------------------------------------------------------
# Paragraph -> Block, with colour detection
# --------------------------------------------------------------------------------------


def _block_from_paragraph(
    para: list[list[TextBox]], pixels: np.ndarray, dpi: float, *, index: int, page_index: int
) -> Block:
    doc_lines: list[Line] = []
    confidences: list[float] = []
    for line_boxes in para:
        spans: list[Span] = []
        line_bbox: BBox | None = None
        for box in line_boxes:
            # numpy float32 -> Python float: DocIR'in numpy taşımaması gerekir / DocIR must not carry numpy types
            x0, y0, x1, y1 = (float(c) for c in box.bbox)
            bbox = BBox(x0, y0, x1, y1)
            line_bbox = bbox if line_bbox is None else line_bbox.union(bbox)
            fg, bg = _box_colors(pixels, bbox)
            size_pt = float((y1 - y0) * 72.0 / dpi)
            # "Arial" rather than the generic "sans-serif": fitting/fontmatch.py's classify()
            # checks its serif hint list before its sans hint list, and "serif" is a substring
            # of "sans-serif", so that literal string misclassifies as serif. "Arial" names a
            # real sans family and resolves correctly through the substitution table instead.
            style = Style(font_family="Arial", size=round(size_pt, 2), color=fg, background=bg)
            spans.append(Span(text=box.text, bbox=bbox, style=style, direction=Direction.LTR))
            confidences.append(float(box.confidence))
        doc_lines.append(Line(spans=spans, bbox=line_bbox))

    block_bbox = doc_lines[0].bbox
    for line in doc_lines[1:]:
        if line.bbox is not None:
            block_bbox = line.bbox if block_bbox is None else block_bbox.union(line.bbox)
    if block_bbox is None:
        block_bbox = BBox(0, 0, 0, 0)

    confidence = min(confidences) if confidences else 1.0
    return Block(
        id=f"img{page_index}#{index}",
        role=BlockRole.BODY,
        bbox=block_bbox,
        lines=doc_lines,
        direction=Direction.LTR,
        confidence=confidence,
        needs_review=confidence < tunables.get("ocr.needs_review_threshold"),
        review_reason=(
            f"OCR güveni düşük ({confidence:.2f})"
            if confidence < tunables.get("ocr.needs_review_threshold") else ""
        ),
    )


def _box_colors(pixels: np.ndarray, bbox: BBox) -> tuple[str, str | None]:
    """Foreground (text) and background colour of a box, via 2-means over its pixels.

    The smaller cluster is assumed to be the text - a text box, by construction, is mostly its
    own background with a minority of ink/glyph pixels.
    """
    x0, y0, x1, y1 = (max(0, int(bbox.x0)), max(0, int(bbox.y0)), int(bbox.x1), int(bbox.y1))
    crop = pixels[y0:y1, x0:x1]
    if crop.size == 0:
        return "#000000", None
    flat = crop.reshape(-1, 3).astype(np.float64)
    if len(flat) < 2:
        color = _to_hex(flat[0]) if len(flat) else "#000000"
        return color, None
    fg, bg = _kmeans2(flat)
    return _to_hex(fg), _to_hex(bg)


def _kmeans2(points: np.ndarray, *, iterations: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Plain 2-means over RGB points. Returns (minority-cluster centroid, majority-cluster
    centroid) i.e. (foreground, background). No sklearn dependency - this project targets a
    small install size and two clusters over a few thousand pixels needs no library."""
    lo = points[np.argmin(points.sum(axis=1))]
    hi = points[np.argmax(points.sum(axis=1))]
    centroids = np.stack([lo, hi])
    labels = None
    for _ in range(iterations):
        dist = np.linalg.norm(points[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(dist, axis=1)
        if labels is not None and np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for k in (0, 1):
            members = points[labels == k]
            if len(members):
                centroids[k] = np.median(members, axis=0)
    counts = np.bincount(labels, minlength=2)
    minority, majority = (0, 1) if counts[0] <= counts[1] else (1, 0)
    return centroids[minority], centroids[majority]


def _to_hex(rgb: np.ndarray) -> str:
    r, g, b = (round(c) for c in rgb[:3])
    r, g, b = (max(0, min(255, v)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"
