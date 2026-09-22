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
from layoutkeep.fitting.growth import free_below, may_grow
from layoutkeep.fitting.measure import TextMeasurer
from layoutkeep.fitting.room import room_below

#: (segment, max_len) -> replacement translation, wired to the real provider by the caller.
Retranslate = Callable[[Segment, int], str]

#: [(segment, max_len), ...] -> {(block_id, max_len): replacement}. One call for many boxes, so the
#: fit can ask for a whole round of shortenings in a single request instead of one per box.
RetranslateMany = Callable[[list[tuple[Segment, int]]], dict[tuple[str, int], str]]

#: Below this rotation a block is drawn horizontally, with `insert_htmlbox` - and only that path
#: can use the room granted below a block (see `fitting/growth.py`).
_ROTATION_EPS = 0.01


#: A block whose measured box is shortened to this height has nothing to draw in: `room_below`
#: takes it down to keep clear of the next block's lines, and no text fits in six points. It is
#: the floor of the shortening rule above, named here so the flag's reason and the box agree.
_MIN_BOX_HEIGHT_PT = 6.0


def fit_pdf_pass(
    doc: Document,
    segments: list[Segment],
    *,
    retranslate: Retranslate,
    mode: FitMode = FitMode.STRICT,
    target_lang: str | None = None,
    on_fitted: Callable[[Segment, Block, object], None] | None = None,
    fetch_many: RetranslateMany | None = None,
) -> dict[str, int] | None:
    """Run the two-directional fit over every translated segment; returns layer counts.

    `on_fitted(segment, block, fit_result)` fires per segment with the engine's verdict, so
    each front-end can write the text/scale back, raise review flags and report progress
    without either duplicating the loop (which is how the CLI and GUI drifted before).

    `target_lang` drives font substitution for the character-budget measurer when a style
    has no `font_path` yet (the writer resolves its own fonts later, at write time).

    `fetch_many` is optional and changes nothing about the result, only the number of requests: the
    pass runs twice, the first time collecting what it would ask for, and those are fetched in one
    call. Without it every overflowing box is its own request, which on a real book is the slowest
    part of a run.
    """
    from layoutkeep.writers.pdf_writer import measure_fit, same_text

    blocks = {b.id: b for _, b in doc.iter_blocks()}
    # Which blocks came from a page with no text layer. Their boxes are OCR's idea of where the
    # glyphs were, widened further by `image_reader._grant_blank_paper` so a longer language has
    # somewhere to go - not the frame the source text filled. Measuring fill against that box
    # asks the model to pad until it covers space the original never used, which invents content
    # (expansion measured 1.47x on a page of computer-systems-Architecture.pdf against the
    # 0.93-1.12x an honest EN->TR run produces). See the `char_budget` argument below.
    from_scan = {b.id: page.scanned for page, b in doc.iter_blocks()}
    page_of = {b.id: page.blocks for page, b in doc.iter_blocks()}
    drawn_of = {b.id: page.images for page, b in doc.iter_blocks()}
    from layoutkeep.core import tunables

    slack = float(tunables.get("write.box_slack_pt"))
    # Before anything is measured: boxes a figure shares a band with are narrowed, so the text
    # re-flowed into them cannot be drawn over the picture. Done here rather than in the writer
    # because the fitting pass and the writer must see the same box - measuring against one and
    # drawing in another is how a block ends up shrunk twice (see `_layout_rect`'s docstring).
    from layoutkeep.fitting.figures import keep_page_off_figures

    off_figure = sum(
        keep_page_off_figures(page.blocks, page.images, clearance=slack) for page in doc.pages
    )
    #: Absent when the setting is 0, so a run that does not want the block to grow pays nothing
    #: for looking.
    grant_limit = float(tunables.get("write.grant_room_pt"))
    measurers: dict[tuple, TextMeasurer | None] = {}
    drawn_fonts: dict[tuple, str | None] = {}
    def run_pass(retranslate_fn: Retranslate, *, apply_result: bool = True) -> list:
        """Walk every segment once with the given asker and return the fit results.

        `apply_result` is False for the collecting pass: its verdicts are the answer "this does not
        fit", not a fit, so reporting them through `on_fitted` would write wrong scales, raise flags
        that the real pass never raises, and double-count the crushed boxes.
        """
        out = []
        report = on_fitted if apply_result else None

        for seg in segments:
            block = blocks.get(seg.block_id)
            if block is None or not seg.translated:
                continue
            # The writer leaves an unchanged block as the source drew it, so there is nothing to fit.
            # Fitting it anyway measured a name in the wider substitute face, shrank it to the floor,
            # flagged it and asked the model to shorten it: 34 of 64 blocks on arXiv 2609.19145's
            # first page were "below the readability floor", its unchanged author names among them.
            if same_text(seg.source, seg.target):
                continue

            # Measured in the face the writer will draw: with no font file resolved, the generic serif
            # (Times) is up to 29% narrower than the Noto Serif the writer substitutes, and a line that
            # "fit" wrapped when drawn and lost its end (held-out PLOS ONE, eight one-line blocks).
            style = _as_drawn(block.dominant_style(), target_lang, drawn_fonts)
            measurer = _measurer_for(measurers, style, target_lang)

            def char_budget(style, bbox, scale, _m=measurer):
                return _m.char_budget(style, bbox, scale)

            # Measured against the room the writer will actually draw in: the slack below is only what
            # the page has free (`fitting.room`), plus the room the page genuinely has under the block
            # (`fitting.growth`) - which is what lets a translation take the second line it needs
            # instead of being shrunk to the floor or flagged. A rotated block is drawn by the
            # `TextWriter` path, which has no such room, so it is measured as before.
            page_blocks = page_of.get(seg.block_id, [])
            missing = slack - room_below(block, page_blocks, slack)
            grant = (
                free_below(block, page_blocks, limit=grant_limit, obstacles=drawn_of.get(seg.block_id, ()))
                if abs(block.rotation) <= _ROTATION_EPS and grant_limit > 0 and may_grow(block)
                else 0.0
            )
            measured_box = (
                BBox(
                    block.bbox.x0, block.bbox.y0, block.bbox.x1,
                    max(
                        block.bbox.y0 + min(block.bbox.height, _MIN_BOX_HEIGHT_PT),
                        block.bbox.y1 - missing + grant,
                    ),
                )
                if missing > 0 or grant > 0 else block.bbox
            )
            result = fit_segment(
                seg,
                style,
                measured_box,
                measure_fit,
                mode=mode,
                retranslate=retranslate_fn,
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
            crushed = measured_box.height <= min(block.bbox.height, _MIN_BOX_HEIGHT_PT) + 0.01
            if result.needs_review and missing > 0 and crushed:
                # A key, not a sentence: the front-ends turn it into the interface's language (the
                # same split `ui.progress.format_phase` uses for phase names), and the completion
                # screen counts it. A box shortened to its floor has nothing to draw in - no text fits
                # in six points - and that is a different problem from a translation that is too long.
                result.review_reason = "box_crushed"
            if report is not None:
                report(seg, block, result)
            out.append(result)
        return out

    if fetch_many is None:
        results = run_pass(retranslate)
    else:
        # Two passes instead of one. The fit discovers which boxes overflow only by trying them, so
        # the first pass runs with a recorder: it returns the text already in hand, which makes
        # `fit_segment` stop after its first question (fit.py breaks when the answer is not shorter)
        # and calls no model at all. What it asked for is then fetched in ONE request, and the
        # second pass fits for real from those answers. Later rounds are rare and still ask singly.
        asked: dict[tuple[str, int], tuple[Segment, int]] = {}

        def record(segment: Segment, budget: int) -> str:
            asked.setdefault((segment.block_id, budget), (segment, budget))
            return segment.target

        run_pass(record, apply_result=False)
        answers = fetch_many(list(asked.values())) if asked else {}

        def replay(segment: Segment, budget: int) -> str:
            hit = answers.get((segment.block_id, budget))
            return hit if hit else retranslate(segment, budget)

        results = run_pass(replay)

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

    summary = summarize(results) if results else None
    if summary is not None:
        # Reported so a run can show how many boxes had to step aside for a picture; a page of
        # them means the fitting line's numbers were earned in narrower columns.
        summary["off_figure"] = off_figure
    return summary


def budget_segments(
    doc: Document,
    segments: list[Segment],
    *,
    target_lang: str | None = None,
    headroom: float = 1.0,
) -> int:
    """Give every segment the character budget of the box it will be drawn in. Returns how many.

    WHY: the model is already told, per segment, to write short enough for `max_len`
    (`providers/openai_compat.py`), and that instruction never fired because the fit was the only
    place that filled the value - i.e. after the translation had already overflowed the box. The
    budget is pure geometry, so it can be known before the first request, and the fit then has far
    less to repair. Same measurer as the fit on purpose: two budgets would drift.

    `headroom` above 1 keeps the budget above the measured box: the model is still steered short,
    but it is not pushed into dropping content to reach a number.
    """
    blocks = {b.id: b for _, b in doc.iter_blocks()}
    drawn_fonts: dict[tuple, str | None] = {}
    measurers: dict[tuple, TextMeasurer | None] = {}
    filled = 0
    for seg in segments:
        block = blocks.get(seg.block_id)
        if block is None or not seg.source:
            continue
        style = _as_drawn(block.dominant_style(), target_lang, drawn_fonts)
        measurer = _measurer_for(measurers, style, target_lang)
        if measurer is None:
            continue
        budget = int(_measurer_budget(measurer, style, block.bbox) * headroom)
        if budget > 0:
            seg.max_len = budget
            filled += 1
    return filled


def _measurer_budget(measurer: TextMeasurer, style, bbox) -> int:
    """The measured budget for one box, or 0 when the measurer cannot say.

    Measured at the box the block already has, without the fit's growth allowance: the first
    translation should aim at what is certainly drawable, and the fit may still grant room later.
    """
    try:
        return int(measurer.char_budget(style, bbox, 1.0))
    except (AttributeError, TypeError, ValueError):
        return 0


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
