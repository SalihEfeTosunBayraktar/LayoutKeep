"""Tests for the shared PDF fitting pass (docs/CONTRACT.md D1/D2 wiring).

`pdf_pass.fit_pdf_pass` is the single loop both front-ends run; `apply_scale` is the
single write-back both use. Strategy-level fitting behaviour (fit_segment layers) is
covered in test_fitting_fit.py; here we pin the pass's own behaviour: which segments
get sent through the engine, what happens to untouched/orphan segments, and how
`apply_scale` writes the verdict onto the block. No network, no real PyMuPDF
document: `measure_fit` is monkeypatched inside `pdf_writer`, the seam the pass uses.
"""

from __future__ import annotations

import pytest

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Segment,
    Span,
    Style,
)
from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass

BOX = BBox(0, 0, 100, 100)


def _style(size: float = 12.0, family: str = "Arial") -> Style:
    return Style(size=size, font_family=family)


def _doc_with_block(
    block_id: str = "b1", text: str = "hello world", size: float = 12.0
) -> Document:
    style = _style(size=size)
    block = Block(
        id=block_id,
        role=BlockRole.BODY,
        bbox=BOX,
        lines=[Line(spans=[Span(text=text, bbox=BOX, style=style)])],
        order=0,
        source_text=text,
    )
    return Document(
        source_lang="en", target_lang="tr", pages=[Page(number=1, width=200, height=200, blocks=[block])]
    )


def _segment(block_id: str, target: str) -> Segment:
    return Segment(block_id=block_id, source="src", target=target)


class TestApplyScale:
    def test_scale_at_or_above_one_is_noop(self):
        doc = _doc_with_block()
        block = next(b for _, b in doc.iter_blocks())
        apply_scale(block, 1.0)
        apply_scale(block, 1.5)
        assert block.lines[0].spans[0].style.size == 12.0

    def test_scale_below_one_shrinks_every_span(self):
        doc = _doc_with_block()
        block = next(b for _, b in doc.iter_blocks())
        apply_scale(block, 0.8)
        assert block.lines[0].spans[0].style.size == pytest.approx(12.0 * 0.8)

    def test_scale_multiplies_across_all_lines(self):
        block = Block(
            id="b1",
            role=BlockRole.BODY,
            bbox=BOX,
            lines=[
                Line(spans=[Span(text="x", bbox=BOX, style=_style(size=10.0))]),
                Line(spans=[Span(text="y", bbox=BOX, style=_style(size=10.0))]),
            ],
            order=0,
            source_text="x\ny",
        )
        apply_scale(block, 0.5)
        sizes = [s.style.size for ln in block.lines for s in ln.spans]
        assert sizes == [5.0, 5.0]


class TestFitPdfPass:
    def test_untouched_and_orphan_segments_are_skipped(self, monkeypatch):
        """No engine call, no on_fitted, no summary when nothing is translatable."""
        calls: list[str] = []

        def fake_measure(*args, **kwargs):  # pragma: no cover - must not run
            calls.append("measure")
            return True, 1.0

        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake_measure)
        doc = _doc_with_block()
        untouched = _segment("b1", "")  # block exists but not translated
        orphan = _segment("ghost", "text")  # block does not exist

        result = fit_pdf_pass(
            doc,
            [untouched, orphan],
            retranslate=lambda seg, m: "x",
        )
        assert result is None
        assert calls == []

    def test_translated_segment_goes_through_engine(self, monkeypatch):
        seen_measure: list[str] = []

        def fake_measure(text, style, bbox, scale_low, rotation=0.0):
            seen_measure.append(text)
            # Long text overflows unless shrunk; the engine then shrinks.
            return (len(text) <= 3), 0.5

        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake_measure)
        doc = _doc_with_block()
        seg = _segment("b1", "uzun çeviri metni sığmıyor buraya")
        fitted: list[tuple[Segment, Block, object]] = []

        result = fit_pdf_pass(
            doc,
            [seg],
            retranslate=lambda seg, m: "kısa",
            on_fitted=lambda s, b, r: fitted.append((s, b, r)),
        )
        assert seen_measure, "measure_fit should have been called for the translated segment"
        assert len(fitted) == 1
        block = fitted[0][1]
        assert block.id == "b1"
        assert result is not None

    def test_on_fitted_receives_fit_verdict_fields(self, monkeypatch):
        def fake_measure(text, style, bbox, scale_low, rotation=0.0):
            return (len(text) <= 2), 1.0

        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake_measure)
        doc = _doc_with_block()
        seg = _segment("b1", "abc")  # fits as-is
        fitted: list[object] = []

        fit_pdf_pass(
            doc,
            [seg],
            retranslate=lambda seg, m: "xy",
            on_fitted=lambda s, b, r: fitted.append(r),
        )
        assert len(fitted) == 1
        assert fitted[0].needs_review is False

    def test_document_with_no_blocks_yields_none(self, monkeypatch):
        monkeypatch.setattr(
            "layoutkeep.writers.pdf_writer.measure_fit",
            lambda *a, **k: (True, 1.0),
        )
        doc = Document(source_lang="en", target_lang="tr", pages=[])
        assert fit_pdf_pass(doc, [_segment("x", "text")], retranslate=lambda s, m: "y") is None
