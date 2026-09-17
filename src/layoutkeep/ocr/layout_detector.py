"""Find a page's regions - paragraph, heading, caption, figure - with a trained layout detector.

WHY. Every grouping rule on the scanned path decided from geometry what a region IS, with a
constant calibrated on one page, and each broke another page. XY-cut (`readers/_segment.py`)
removed the page-size assumptions but still cannot tell a heading from a formula, or a
paragraph break from a figure label. That is a learned judgement, and a model trained on many
document types makes it without any constant tuned to this project's two documents.

WHICH MODEL, AND WHY. `docling-project/docling-layout-heron-onnx`, IBM Docling's default layout
model (RT-DETRv2, 42.9M parameters), checked at the source on 2026-09-16:

  * Apache-2.0, so it can ship inside an AGPL application. Surya and LayoutLMv3 cannot (their
    weights forbid commercial use); MinerU's licence is a custom one.
  * An official ONNX export exists, so it runs on the `onnxruntime` RapidOCR already brings -
    no PyTorch. Box decoding is inside the graph: it takes uint8 pixels and the original size
    as (width, height), and returns labels, boxes in original pixels, and scores.
  * Its own report (arXiv 2509.11720) gives 78% mAP for the best variant. That is good, not
    perfect, and was measured on the report's benchmarks, not on our documents - which is why
    this is judged on `tools/audit/page_eval.py` and the style fixtures before it replaces
    anything.

Measured here on the book's pages 22 and 61 at 100 DPI: 0.33 s a page on CPU, every paragraph
its own `text` box, margin keywords as separate small `text` boxes, and the figure, its caption
and a section heading labelled correctly.

WHAT IT DOES NOT DO. It returns regions, not reading order - Docling itself orders regions with
a rule-based pass (`reading_order_rb`), not a model - and not type sizes. Order stays with
XY-cut; sizes stay with the recogniser.

It is optional and fail-safe, like `layout_vlm`: with no model file, `load_detector` returns
None and the page is read exactly as before.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from layoutkeep.core.docir import BlockRole

#: Overrides where the model file is looked for.
ENV_MODEL = "LAYOUTKEEP_LAYOUT_MODEL"

#: The model's own input size (its `preprocessor_config.json`).
_INPUT_SIZE = 640

#: Below this a detection is not used. Docling's own example uses 0.6; the book's margin
#: keywords score 0.77-0.84 and a page header's folio 0.81, so 0.5 keeps them with room.
DEFAULT_THRESHOLD = 0.5

#: The model's classes (its `config.json`), in id order.
LABELS: tuple[str, ...] = (
    "caption", "footnote", "formula", "list_item", "page_footer", "page_header", "picture",
    "section_header", "table", "text", "title", "document_index", "code",
    "checkbox_selected", "checkbox_unselected", "form", "key_value_region",
)

LABEL_TO_ROLE: dict[str, BlockRole] = {
    "caption": BlockRole.CAPTION,
    "footnote": BlockRole.FOOTNOTE,
    "formula": BlockRole.FORMULA,
    "list_item": BlockRole.LIST,
    "page_footer": BlockRole.FOOTER,
    "page_header": BlockRole.HEADER,
    "picture": BlockRole.FIGURE,
    "section_header": BlockRole.HEADING,
    "table": BlockRole.TABLE,
    "text": BlockRole.BODY,
    "title": BlockRole.TITLE,
    "document_index": BlockRole.BODY,
    "code": BlockRole.CODE,
}

#: Regions whose text is not prose to be grouped into one paragraph: a picture's labels, a
#: table's cells and an index's entries are many small independent pieces, one block per line.
NOT_A_PARAGRAPH: frozenset[str] = frozenset(
    {"picture", "table", "form", "key_value_region", "document_index"}
)


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    """One detected region, in the pixels of the image it was detected on."""

    label: str
    bbox: tuple[float, float, float, float]
    score: float


class LayoutDetector(Protocol):
    def detect(self, image: Image.Image) -> list[LayoutRegion]: ...


def default_model_path() -> Path:
    override = os.environ.get(ENV_MODEL)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or Path.home()
    return Path(base) / "LayoutKeep" / "models" / "docling-layout-heron-onnx" / "model.onnx"


class HeronDetector:
    """The ONNX model, loaded once and reused for every page."""

    def __init__(self, model_path: Path, *, threshold: float = DEFAULT_THRESHOLD) -> None:
        import onnxruntime  # deferred: importing this module must not require the OCR extra

        self._session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self._threshold = threshold

    def detect(self, image: Image.Image) -> list[LayoutRegion]:
        rgb = image.convert("RGB")
        pixels = np.asarray(rgb.resize((_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR))
        labels, boxes, scores = self._session.run(
            None,
            {
                "images": pixels.transpose(2, 0, 1)[None],
                "orig_target_sizes": np.array([[rgb.width, rgb.height]], dtype=np.int64),
            },
        )
        regions: list[LayoutRegion] = []
        for label, box, score in zip(labels[0], boxes[0], scores[0], strict=True):
            if score < self._threshold or not 0 <= int(label) < len(LABELS):
                continue
            x0, y0, x1, y1 = (float(v) for v in box)
            regions.append(LayoutRegion(LABELS[int(label)], (x0, y0, x1, y1), float(score)))
        return regions


def load_detector(model_path: Path | None = None) -> LayoutDetector | None:
    """The detector, or None if the model is not installed or cannot be loaded."""
    path = model_path or default_model_path()
    if not path.is_file():
        return None
    try:
        return HeronDetector(path)
    except Exception:  # noqa: BLE001 - an unloadable model means "no detector", never a crash
        return None


#: Labels that box a stretch of running text. Duplicates are resolved among these only; a text
#: region inside a picture, a table or a form is hierarchy, not duplication.
PROSE: frozenset[str] = frozenset(
    {"caption", "footnote", "list_item", "page_footer", "page_header", "section_header", "text",
     "title", "document_index", "code", "formula"}
)

#: Two boxes overlapping this much (intersection over the smaller box) are the same text boxed
#: twice. High on purpose: a heading directly above a paragraph touches it but barely overlaps.
_SAME_TEXT = 0.8


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _share_of_smaller(a: LayoutRegion, b: LayoutRegion) -> float:
    ix = max(0.0, min(a.bbox[2], b.bbox[2]) - max(a.bbox[0], b.bbox[0]))
    iy = max(0.0, min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1]))
    smaller = min(_area(a.bbox), _area(b.bbox))
    return ix * iy / smaller if smaller > 0 else 0.0


def resolve_duplicates(regions: list[LayoutRegion]) -> list[LayoutRegion]:
    """Keep one box per stretch of text.

    The model boxes the same text twice in two ways, both seen in
    `tests/layout_eval/2026-09-16_heron_pure/`:

      * a loose box around several paragraphs beside a tight box for each (A4 fixture: 0.66
        over all three, 0.76-0.80 for each). The loose one is dropped: a box that holds two or
        more other prose boxes is a union of them, not a block of its own.
      * two near-identical boxes with different labels - a symbol-list entry as both `text` and
        `list_item` (NASA report, 107 duplicates on five pages). The higher-scoring one is kept,
        because the choice between them is exactly what the score expresses.
    """
    prose = [r for r in regions if r.label in PROSE]
    others = [r for r in regions if r.label not in PROSE]

    unions = {
        id(outer) for outer in prose
        if sum(
            1 for inner in prose
            if inner is not outer and _area(inner.bbox) < _area(outer.bbox)
            and _share_of_smaller(inner, outer) >= _SAME_TEXT
        ) >= 2
    }
    kept: list[LayoutRegion] = []
    for region in sorted((r for r in prose if id(r) not in unions), key=lambda r: -r.score):
        if all(_share_of_smaller(region, k) < _SAME_TEXT for k in kept):
            kept.append(region)
    return kept + others
