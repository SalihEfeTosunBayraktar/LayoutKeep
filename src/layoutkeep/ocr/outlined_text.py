"""Detection of drawn/outlined text: text visible on a rendered page that has no matching entry
in the page's own text layer.

Real documents sometimes carry text as vector outlines rather than as font-set characters - a
logo, an exported design, glyphs converted to curves for print. A PDF's text layer
(`Page.get_text()`) does not see this text at all: it is not mis-read or low-confidence, it
simply is not there, and a naive pipeline would "translate" the page while silently leaving that
word in the source language.

Detection strategy, chosen after measurement (see tests/test_outlined_text.py): counting path
primitives (curves vs. lines) does not distinguish letterforms from illustration - a word in this
project's own outlined-text fixture turned out to be line-heavy, and a curve-heavy drawing turned
out to be a cake, the opposite of what a shape heuristic would predict. What works instead is
render-and-diff: OCR the rendered page and compare what it reads against what the text layer
reports. Text OCR sees that the text layer does not is drawn text.

This module only knows about a rendered image and a plain-text string - it never imports pymupdf
(reserved to readers/pdf_reader.py and writers/pdf_writer.py, see CONTRACT.md S4). The PDF-side
seam (rendering a page to an image, calling this, and deciding what to do with the result) is a
pdf_reader.py concern and out of this module's ownership.
"""

from __future__ import annotations

import re

from layoutkeep.ocr.engine import ImageSource, OcrEngine, RapidOcrEngine, TextBox

#: Letters-only tokens (drops punctuation, digits, whitespace) so comparison is not thrown off by
#: OCR/text-layer disagreement on things like hyphenation or stray page-number digits.
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

#: OCR reads below this confidence are dropped rather than reported: a garbled read is not
#: trustworthy evidence that the word does not exist in the text layer, it is just a bad read.
_MIN_CONFIDENCE = 0.5


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def find_outlined_text(
    page_image: ImageSource,
    extracted_text: str,
    *,
    engine: OcrEngine | None = None,
    min_confidence: float = _MIN_CONFIDENCE,
) -> list[TextBox]:
    """Return the OCR boxes on `page_image` whose text does not appear in `extracted_text`.

    A box counts as "present in the layer" if ANY of its word tokens also appear there - OCR and
    a text layer rarely agree character-for-character (whitespace, ligatures, hyphenation), so
    matching is deliberately permissive. That trades a few missed detections (a genuinely
    outlined word that happens to share a common token with the layer) for fewer false positives,
    since a false positive here would duplicate content that is already correctly translatable
    through the text layer - the worse of the two mistakes.

    `extracted_text` should be the same page's `Page.get_text()` (or equivalent). Returns an
    empty list when nothing looks drawn-only; that is the expected result for ordinary pages and
    must be measured to stay low (see tests/test_outlined_text.py for the false-positive rate).
    """
    engine_ = engine if engine is not None else RapidOcrEngine()
    boxes = engine_.recognize(page_image)
    layer_tokens = _tokens(extracted_text)

    missing: list[TextBox] = []
    for box in boxes:
        if box.confidence < min_confidence:
            continue
        box_tokens = _tokens(box.text)
        if not box_tokens or box_tokens & layer_tokens:
            continue
        missing.append(box)
    return missing
