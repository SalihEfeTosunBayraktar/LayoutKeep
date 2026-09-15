"""On a scanned page the source text is painted into the page image, so it has to be covered.

`write_pdf` removes source text with PDF redaction, and calls `apply_redactions` with
`PDF_REDACT_IMAGE_NONE` on purpose: without it every figure that merely overlaps a text block
would be destroyed. On a scanned page that guarantee has the opposite effect - the text *is* the
image, redaction removes nothing, and the translation is drawn on top of the original words.
Rendering `computer-systems-Architecture.pdf` that way produced pages with both languages
overprinted on each other, illegible.

These tests measure the ink, not the intent: they count dark pixels where the source text was
and require them to actually go away.
"""

from __future__ import annotations

import numpy as np
import pymupdf
import pytest
from PIL import Image

from layoutkeep.core.docir import Document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf
from tests.test_pdf_reader_scanned import PAGE_H_PT, PAGE_W_PT, build_scanned_pdf

#: What the "translation" replaces every block with. Short on purpose: the point of these tests
#: is whether the ORIGINAL ink is gone, so the replacement must not deposit much of its own.
STAND_IN = "x"
#: Below this the pixel counts as ink rather than paper.
_DARK = 160


def _ink(page: pymupdf.Page, clip: pymupdf.Rect | None = None) -> int:
    pix = page.get_pixmap(dpi=150, clip=clip)
    grey = np.array(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L"))
    return int((grey < _DARK).sum())


def _replace_text(doc: Document, replacement: str = STAND_IN) -> None:
    """Stand in for the translation step without needing a provider."""
    for _page, block in doc.iter_blocks():
        for line_index, line in enumerate(block.lines):
            for span_index, span in enumerate(line.spans):
                span.text = replacement if (line_index == 0 and span_index == 0) else ""


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("scanned_write")
    src = tmp / "scan.pdf"
    build_scanned_pdf(src)
    doc = read_pdf(src)
    assert doc.pages[0].blocks, "fixture produced no OCR blocks; reader-side problem, not writer"
    _replace_text(doc)
    out = tmp / "out.pdf"
    write_pdf(doc, src, out)
    return src, out, doc


def test_reader_marks_the_page_as_scanned(rendered) -> None:
    """The writer's whole branch hangs off this flag, so pin it separately - if it regresses the
    ink assertions below would still fail but would not say why."""
    _src, _out, doc = rendered
    assert doc.pages[0].scanned is True


def test_source_text_is_covered(rendered) -> None:
    """The original words must be gone, not merely overdrawn."""
    src_path, out_path, _doc = rendered
    with pymupdf.open(src_path) as src_pdf, pymupdf.open(out_path) as out_pdf:
        before = _ink(src_pdf[0])
        after = _ink(out_pdf[0])
    # The replacement is a single "x" per block, so nearly all the source ink should be gone.
    assert after < before * 0.35, (
        f"scanned source text survived: {before} dark px before, {after} after"
    )


def test_untouched_area_is_preserved(rendered) -> None:
    """Covering the text must not blank the rest of the page: a scanned page carries figures and
    rules that no block claims, and painting the whole scan white would 'fix' the overprint by
    throwing the document away."""
    src_path, out_path, _doc = rendered
    margin = pymupdf.Rect(0, PAGE_H_PT * 0.75, PAGE_W_PT, PAGE_H_PT)
    with pymupdf.open(src_path) as src_pdf, pymupdf.open(out_path) as out_pdf:
        assert _ink(src_pdf[0], margin) == _ink(out_pdf[0], margin)


def test_translation_is_drawn(rendered) -> None:
    """And the replacement text has to actually be on the page, as real selectable text."""
    _src, out_path, _doc = rendered
    with pymupdf.open(out_path) as out_pdf:
        assert STAND_IN in out_pdf[0].get_text()
