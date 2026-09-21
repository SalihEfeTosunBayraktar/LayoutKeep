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


class TestBatchedFetch:
    """`fetch_many` changes how many requests go out, never what the fit decides.

    The batched path walks the segments twice: a collecting pass that asks for nothing and a real
    pass that fits from the answers. The collecting pass must stay silent - its verdicts are the
    answer "this does not fit", so reporting them writes a wrong scale onto the block, raises flags
    the real pass never raises and counts crushed boxes twice.
    """

    @staticmethod
    def _fake_measure(text, style, bbox, scale_low, rotation=0.0):
        return (len(text) <= 3), 1.0

    def _run(self, monkeypatch, *, batched: bool):
        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", self._fake_measure)
        doc = _doc_with_block()
        seg = _segment("b1", "uzun çeviri metni sığmıyor buraya")
        asked: list[tuple[str, int]] = []
        verdicts: list[tuple[str, bool]] = []

        def on_fitted(s, _b, r):
            verdicts.append((s.block_id, bool(r.needs_review)))

        if batched:
            def fetch_many(pairs):
                asked.extend((s.block_id, budget) for s, budget in pairs)
                return {(s.block_id, budget): "kısa" for s, budget in pairs}

            result = fit_pdf_pass(
                doc, [seg], retranslate=lambda s, m: "kısa", fetch_many=fetch_many, on_fitted=on_fitted
            )
        else:
            result = fit_pdf_pass(doc, [seg], retranslate=lambda s, m: "kısa", on_fitted=on_fitted)
        return result, asked, verdicts

    def test_the_batched_pass_asks_once_and_decides_the_same(self, monkeypatch):
        plain, _, plain_verdicts = self._run(monkeypatch, batched=False)
        batched, asked, batched_verdicts = self._run(monkeypatch, batched=True)

        assert asked, "the collecting pass must have asked for the overflowing box"
        assert batched == plain, f"the same fit is expected either way: {batched} vs {plain}"
        assert batched_verdicts == plain_verdicts

    def test_the_collecting_pass_does_not_report(self, monkeypatch):
        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", self._fake_measure)
        doc = _doc_with_block()
        seg = _segment("b1", "uzun çeviri metni sığmıyor buraya")
        seen: list[object] = []

        fit_pdf_pass(
            doc,
            [seg],
            retranslate=lambda s, m: "kısa",
            fetch_many=lambda pairs: {},
            on_fitted=lambda s, b, r: seen.append(r),
        )
        assert len(seen) == 1, f"on_fitted must fire once per segment, fired {len(seen)} times"


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
            return (len(text) <= 15), 1.0

        monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake_measure)
        doc = _doc_with_block()
        # Long enough to be worth compressing when it does not fit: a text under
        # `_MIN_SHORTEN_CHARS` never reaches the ladder (see test_fitting_fit).
        seg = _segment("b1", "a much longer translation than the box can hold at any size")
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


class TestReviewReasons:
    """What a flag says is part of the product - it is the line the review list shows.

    Measured on the book: most flags are not text that could not be shortened, they are boxes the
    pass had to crush to keep clear of the next block (`room_below`), and a 6pt box fits nothing.
    Telling the user "shrinking was not enough" then sends them to the wrong knob.
    """

    def test_a_crushed_box_says_the_box_was_the_problem(self, monkeypatch) -> None:
        doc = _doc_with_block()
        page = doc.pages[0]
        # A second block starting deep inside the first: room_below goes strongly negative, so the
        # measured box is shortened to its 6pt floor and nothing can fit there.
        under = Block(
            id="b2",
            role=BlockRole.BODY,
            bbox=BBox(0, 9, 100, 150),
            lines=[Line(spans=[Span(text="under", bbox=BBox(0, 9, 100, 150), style=_style())])],
            order=1,
            source_text="under",
        )
        page.blocks.append(under)
        seen: list[object] = []

        fit_pdf_pass(
            doc,
            [_segment("b1", "uzun bir çeviri metni kutuya sığmıyor")],
            retranslate=lambda segment, budget: segment.target,
            on_fitted=lambda _s, _b, result: seen.append(result),
        )

        assert seen, "the block must reach the engine"
        assert seen[0].needs_review, seen[0]
        # The engine reports a key; the front-ends own the words (see core/review.py).
        assert seen[0].review_reason == "box_crushed", seen[0].review_reason

    def test_an_ordinary_overflow_keeps_the_generic_reason(self) -> None:
        """A block with room below it is a text problem, and must not claim otherwise."""
        doc = _doc_with_block()
        seen: list[object] = []

        fit_pdf_pass(
            doc,
            [_segment("b1", "uzun bir çeviri metni kutuya sığmıyor " * 6)],
            retranslate=lambda segment, budget: segment.target,
            on_fitted=lambda _s, _b, result: seen.append(result),
        )

        assert seen and seen[0].needs_review
        assert seen[0].review_reason == "", seen[0].review_reason
