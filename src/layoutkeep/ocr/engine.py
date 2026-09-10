"""OCR engine abstraction.

`recognize(image) -> list[TextBox]` is the whole contract. `readers/image_reader.py` merges
the returned boxes into lines and paragraphs; nothing here knows about DocIR.

`RapidOcrEngine` is the default (and, for Phase 2, the only) implementation: rapidocr + ONNX
Runtime, Apache-2.0, CPU-only, no PyTorch/Paddle (see .claude/agents/lk-ocr.md for why - Surya's
RAIL-M weights and rapidocr-onnxruntime's dead Python-3.13 support were both ruled out). Model
weights are NOT bundled with this package: rapidocr downloads them to its own package directory
under the active environment (observed at
`<venv>/Lib/site-packages/rapidocr/models/*.onnx`, ~31 MB total) the first time `RapidOCR()` is
constructed, and reuses them afterwards. The packaged application is the exception: it carries
those weights and points the library at them (`bundled_model_params`), because a one-file build
has no package directory to download into and an offline user would get nothing but an error. `RapidOcrEngine` defers that construction to the first
`recognize()` call so importing this module never triggers a download.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

#: What `recognize()` accepts besides an already-open `Image.Image`: a filesystem path (str or
#: `Path`) or raw encoded image bytes. A path is the obvious first thing a caller reaches for -
#: forcing everyone to `Image.open()` first is friction with no benefit, since we open it anyway.
ImageSource = str | Path | bytes | Image.Image


def _to_image(source: ImageSource) -> Image.Image:
    """Normalise any accepted source into an open `Image.Image`."""
    if isinstance(source, Image.Image):
        return source
    if isinstance(source, bytes):
        return Image.open(io.BytesIO(source))
    return Image.open(source)  # str or Path


@dataclass(slots=True)
class TextBox:
    """One piece of text an OCR engine found, in source-image pixel coordinates."""

    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    confidence: float  # 0.0-1.0, straight from the engine - never invented downstream


class OcrEngine(Protocol):
    """What `readers/image_reader.py` needs from an OCR backend. Swappable per platform."""

    def recognize(self, image: ImageSource) -> list[TextBox]:
        """Detect and recognize text in `image` - a path, raw encoded bytes, or an already-open
        `Image.Image`. Returns boxes in reading-model order (not necessarily final reading order
        - that is `image_reader.py`'s job)."""
        ...


#: Which of the three bundled models is which. rapidocr names them after the architecture, and
#: the names change between versions, so they are matched on the part that does not: the stage.
_MODEL_ROLES = (("Det", "det"), ("Rec", "rec"), ("Cls", "cls"))


def bundled_model_params(root: Path | None = None) -> dict[str, str]:
    """Point rapidocr at the weights packaged beside the executable, if there are any.

    In a one-file build the package directory rapidocr looks in does not exist, so it decides
    the models are missing and downloads them - which fails for anyone offline and re-downloads
    31 MB for everyone else. The spec puts the weights under `_MEIPASS/rapidocr/models`; this
    hands their paths over explicitly rather than hoping the library guesses the same place.

    Returns an empty mapping when not running from a bundle, which leaves the library's own
    behaviour untouched for a development run.
    """
    base = root or getattr(sys, "_MEIPASS", None)
    if base is None:
        return {}
    models = Path(base) / "rapidocr" / "models"
    if not models.is_dir():
        return {}

    params: dict[str, str] = {}
    for section, stage in _MODEL_ROLES:
        found = sorted(path for path in models.glob("*.onnx") if stage in path.name.lower())
        if found:
            params[f"{section}.model_path"] = str(found[0])
    return params


class RapidOcrEngine:
    """Default OCR backend: rapidocr running on ONNX Runtime, CPU only."""

    def __init__(self) -> None:
        self._ocr = None  # lazy: constructing RapidOCR() loads/downloads model weights

    def _engine(self):
        if self._ocr is None:
            from rapidocr import RapidOCR

            params = bundled_model_params()
            self._ocr = RapidOCR(params=params) if params else RapidOCR()
        return self._ocr

    def recognize(self, image: ImageSource) -> list[TextBox]:
        import numpy as np

        result = self._engine()(np.array(_to_image(image).convert("RGB")))
        if result.boxes is None:
            return []
        boxes: list[TextBox] = []
        for polygon, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            boxes.append(
                TextBox(
                    text=text,
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=float(score),
                )
            )
        return boxes
