"""The one PDF fitting pass both front-ends run (CLI and the desktop worker).

Lives in `fitting/` but is PDF-specific glue: it wires `fit_segment` (D3, pure strategy) to
`pdf_writer.measure_fit` (the real PyMuPDF measurement seam, D1/D2) and to a provider-backed
`retranslate` callback. Neither the CLI nor the UI worker is allowed to reimplement this
(see test_ui_worker.py's precedent: the GUI stack must behave exactly like the CLI's).

The pass is two-directional since the engine is: overflow asks for a shorter rendering,
under-fill (the EN->TR 0.64x tail) asks for a longer one that still fits. Both iterate up
to `MAX_RETRANSLATE_ROUNDS` rounds, converging on the budget the last round revealed.
"""

from __future__ import annotations

from collections.abc import Callable

from layoutkeep.core.docir import Block, Document, Segment
from layoutkeep.fitting.fit import FitMode, fit_segment, summarize
from layoutkeep.fitting.measure import TextMeasurer

#: (segment, max_len) -> replacement translation, wired to the real provider by the caller.
Retranslate = Callable[[Segment, int], str]


def fit_pdf_pass(
    doc: Document,
    segments: list[Segment],
    *,
    retranslate: Retranslate,
    mode: FitMode = FitMode.STRICT,
    target_lang: str | None = None,
    on_fitted: Callable[[Segment, Block, object], None] | None = None,
) -> dict[str, int] | None:
    """Run the two-directional fit over every translated segment; returns layer counts.

    `on_fitted(segment, block, fit_result)` fires per segment with the engine's verdict, so
    each front-end can write the text/scale back, raise review flags and report progress
    without either duplicating the loop (which is how the CLI and GUI drifted before).

    `target_lang` drives font substitution for the character-budget measurer when a style
    has no `font_path` yet (the writer resolves its own fonts later, at write time).
    """
    from layoutkeep.writers.pdf_writer import measure_fit

    blocks = {b.id: b for _, b in doc.iter_blocks()}
    measurers: dict[tuple, TextMeasurer | None] = {}
    results = []

    for seg in segments:
        block = blocks.get(seg.block_id)
        if block is None or not seg.translated:
            continue

        style = block.dominant_style()
        measurer = _measurer_for(measurers, style, target_lang)

        def char_budget(style, bbox, scale, _m=measurer):
            return _m.char_budget(style, bbox, scale)

        result = fit_segment(
            seg,
            style,
            block.bbox,
            measure_fit,
            mode=mode,
            retranslate=retranslate,
            # Without a real budget the engine's under-fill direction has no honest
            # reference and stays silent - the whole point of this pass.
            char_budget=char_budget if measurer is not None else None,
            rotation=block.rotation,
        )
        if on_fitted is not None:
            on_fitted(seg, block, result)
        results.append(result)

    return summarize(results) if results else None


def apply_scale(block: Block, scale: float) -> None:
    """Shrink a block's type to the size the fitting engine said would fit.

    Horizontal blocks go through `insert_htmlbox`, which shrinks on its own, so this is belt and
    braces there. Rotated blocks are drawn with `TextWriter`, which has no such safety net - for
    those this is the only thing standing between a fitted result and an overflow. Lives here
    (not in a front-end) so the CLI and the desktop worker apply the identical write-back.
    """
    if scale >= 1.0:
        return
    for line in block.lines:
        for span in line.spans:
            span.style.size *= scale


def _measurer_for(
    measurers: dict[tuple, TextMeasurer | None], style, target_lang: str | None
) -> TextMeasurer | None:
    """One TextMeasurer per style key, so a document with two fonts measures twice.

    Returns None (measuring unavailable) rather than raising: a font that cannot be loaded
    must disable the char budget - and with it the expansion direction - for that style,
    not kill the whole fitting pass. Shrink and retranslation-shorter still work through
    `measure_fit`, which has its own generic-family fallback.
    """
    key = (
        style.font_path or style.font_family or "",
        style.bold,
        style.italic,
    )
    if key in measurers:
        return measurers[key]
    from layoutkeep.fitting.fontmatch import resolve_font

    source = style.font_path
    if source is None:
        try:
            match = resolve_font(
                style.font_family or "sans-serif",
                target_lang or "en",
                bold=style.bold,
                italic=style.italic,
            )
            source = match.resolved_path
        except Exception:  # noqa: BLE001 - bilincli: cozulemeyen font pasi oldurmesin
            measurers[key] = None
            return None
    if source is None:
        measurers[key] = None
        return None
    try:
        measurer = TextMeasurer(source)
    except Exception:  # noqa: BLE001 - bilincli: bozuk font metrikleri pasi oldurmesin
        measurer = None
    measurers[key] = measurer
    return measurer
