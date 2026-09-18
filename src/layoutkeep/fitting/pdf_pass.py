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

import dataclasses
from collections.abc import Callable

from layoutkeep.core.docir import BBox, Block, Document, Segment
from layoutkeep.fitting.fit import FitMode, fit_segment, summarize
from layoutkeep.fitting.measure import TextMeasurer
from layoutkeep.fitting.room import room_below

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
    # Which blocks came from a page with no text layer. Their boxes are OCR's idea of where the
    # glyphs were, widened further by `image_reader._grant_blank_paper` so a longer language has
    # somewhere to go - not the frame the source text filled. Measuring fill against that box
    # asks the model to pad until it covers space the original never used, which invents content
    # (expansion measured 1.47x on a page of computer-systems-Architecture.pdf against the
    # 0.93-1.12x an honest EN->TR run produces). See the `char_budget` argument below.
    from_scan = {b.id: page.scanned for page, b in doc.iter_blocks()}
    page_of = {b.id: page.blocks for page, b in doc.iter_blocks()}
    from layoutkeep.core import tunables

    slack = float(tunables.get("write.box_slack_pt"))
    measurers: dict[tuple, TextMeasurer | None] = {}
    drawn_fonts: dict[tuple, str | None] = {}
    results = []

    for seg in segments:
        block = blocks.get(seg.block_id)
        if block is None or not seg.translated:
            continue

        # Measured in the face the writer will draw: with no font file resolved, the generic serif
        # (Times) is up to 29% narrower than the Noto Serif the writer substitutes, and a line that
        # "fit" wrapped when drawn and lost its end (held-out PLOS ONE, eight one-line blocks).
        style = _as_drawn(block.dominant_style(), target_lang, drawn_fonts)
        measurer = _measurer_for(measurers, style, target_lang)

        def char_budget(style, bbox, scale, _m=measurer):
            return _m.char_budget(style, bbox, scale)

        # Measured against the room the writer will actually draw in: the slack below is only what
        # the page has free (`fitting.room`), so a box with less is measured that much shorter.
        page_blocks = page_of.get(seg.block_id, [])
        missing = slack - room_below(block, page_blocks, slack)
        measured_box = (
            BBox(
                block.bbox.x0, block.bbox.y0, block.bbox.x1,
                max(block.bbox.y0 + min(block.bbox.height, 6.0), block.bbox.y1 - missing),
            )
            if missing > 0 else block.bbox
        )
        result = fit_segment(
            seg,
            style,
            measured_box,
            measure_fit,
            mode=mode,
            retranslate=retranslate,
            # Without a real budget the engine's under-fill direction has no honest
            # reference and stays silent - the whole point of this pass. A scanned page has no
            # honest reference either, for the reason `from_scan` records, so it is silenced the
            # same way. The overflow direction is unaffected: it falls back to a length-based
            # budget, so text that does not fit is still shortened.
            char_budget=(
                char_budget if measurer is not None and not from_scan.get(seg.block_id) else None
            ),
            rotation=block.rotation,
        )
        if on_fitted is not None:
            on_fitted(seg, block, result)
        results.append(result)

    if mode is FitMode.REFLOW and any(r.reflow for r in results):
        from layoutkeep.fitting.elastic_flow import ElasticFlowEngine, compute_required_expansion

        expansions = {
            r_seg.block_id: compute_required_expansion(
                r.text, blocks[r_seg.block_id].dominant_style(), blocks[r_seg.block_id].bbox, measure_fit
            )
            for r_seg, r in zip(segments, results, strict=False)
            if r.reflow and r_seg.block_id in blocks
        }
        engine = ElasticFlowEngine()
        for page in doc.pages:
            page_h = getattr(page, "height", 842.0) or 842.0
            page_exp = {b.id: expansions[b.id] for b in page.blocks if b.id in expansions and expansions[b.id] > 0}
            if page_exp:
                engine.reflow_column(page.blocks, page_exp, page_height=page_h)

    return summarize(results) if results else None


def _as_drawn(style, target_lang: str | None, cache: dict[tuple, str | None]):
    """`style` with the font file the writer will substitute for it, when it has none yet.

    The same resolution the writer makes (`fontmatch.resolve_font`, with the source's serif flag),
    short of reusing a PDF's own embedded font, which only the writer can open - there a substitute
    is measured, which errs on the wide side. The block's own style is not changed.
    """
    if style.font_path or not target_lang:
        return style
    key = (style.font_family, style.bold, style.italic, style.serif)
    if key not in cache:
        from layoutkeep.fitting.fontmatch import resolve_font

        try:
            match = resolve_font(
                style.font_family or "sans-serif", target_lang,
                bold=style.bold, italic=style.italic, serif_hint=style.serif,
            )
            cache[key] = match.resolved_path
        except Exception:  # noqa: BLE001 - an unresolvable font keeps the generic measurement
            cache[key] = None
    path = cache[key]
    return dataclasses.replace(style, font_path=path) if path else style


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
