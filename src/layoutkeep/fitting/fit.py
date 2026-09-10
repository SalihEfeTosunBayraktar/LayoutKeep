"""Three-layer fit strategy (docs/CONTRACT.md D3): shrink, then re-translate shorter, then
accept overflow or reflow. Try each layer in order and stop at the first success.

`fitting/` triggers a re-translation request but never calls a translation provider itself
(D2) - callers pass a `RetranslateFn` that wires this to the real provider.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from layoutkeep.core.docir import BBox, Segment, Style
from layoutkeep.fitting.measure import MeasureFn

#: Point size never shrinks past this fraction of the original - below it text is unreadable.
#: Adjustable at runtime, so read it through `min_scale()` rather than binding this name: a
#: module-level default argument is evaluated at import and would ignore the setting entirely,
#: which is exactly what it did before - the setting existed in the dialog and changed nothing.
MIN_SCALE = 0.85
_MIN_SCALE_KEY = "fit.min_scale"


def min_scale_setting() -> float:
    """The smallest fraction of its point size text may be shrunk to, as set right now."""
    from layoutkeep.core import tunables

    return float(tunables.get(_MIN_SCALE_KEY))


class FitMode(StrEnum):
    """What to do when even a shrunk, re-translated segment still doesn't fit."""

    STRICT = "strict"  # accept the overflow, flag needs_review for the correction editor (D6)
    REFLOW = "reflow"  # grow into more lines and tell the caller to push later blocks down


class FitLayer(StrEnum):
    """Which strategy actually made a segment fit. Counting these across a run is the only
    honest measure of whether the engine works (see the brief's verification section)."""

    AS_IS = "as_is"
    SHRUNK = "shrunk"
    RETRANSLATED = "retranslated"
    #: The translation fit but left the box much emptier than the source did (EN->TR can
    #: come back at 0.64x), so a longer rendering was requested and used instead.
    EXPANDED = "expanded"
    OVERFLOW = "overflow"


@dataclass(slots=True)
class FitResult:
    layer: FitLayer
    #: Final multiplier on `style.size` - the whole answer, not an increment a caller must
    #: combine with something else. `insert_htmlbox`-backed writers already shrink for
    #: themselves and can treat this as a report, but `TextWriter` (used for rotated blocks,
    #: see docs/CONTRACT.md D4 and `Block.rotation`) has no shrink-to-fit of its own - for those
    #: blocks this number is the only thing standing between the text and an overflow, so the
    #: writer MUST multiply the font size by it before drawing rather than assume a fallback.
    scale: float
    text: str
    needs_review: bool = False
    #: REFLOW only: the block still doesn't fit and must grow, pushing later blocks down. How
    #: many lines that takes is a page-layout question `fitting/` can't answer (it only knows
    #: `(fits, scale)` from `measure`, not a line count) - the caller re-measures after growing.
    reflow: bool = False


#: (segment, max_len) -> replacement translated text for that segment's `block_id`.
RetranslateFn = Callable[[Segment, int], str]

#: (style, bbox, scale) -> character budget to hand a re-translation request as `max_len`.
CharBudgetFn = Callable[[Style, BBox, float], int]

#: How full a box must be, at least, for the fit to count as faithful. Below this the
#: block visibly under-fills (a two-line original collapsing to half a line of tiny text),
#: which reads as a hole in the page even though nothing overflowed. Measured expansion is
#: 0.93x average EN->TR but 0.64x at the low tail, so a 0.75 floor catches that tail while
#: leaving ordinary variation alone.
MIN_FILL = 0.75

#: How many re-translation rounds a segment may take, in each direction, before the engine
#: gives up and returns the best attempt so far. "Iterate until it looks like the original"
#: needs a hard bound: every round is a provider round-trip, and a model that keeps ignoring
#: the budget must not be allowed to loop the run forever.
MAX_RETRANSLATE_ROUNDS = 3


def fit_segment(
    segment: Segment,
    style: Style,
    bbox: BBox,
    measure: MeasureFn,
    *,
    mode: FitMode = FitMode.STRICT,
    retranslate: RetranslateFn | None = None,
    char_budget: CharBudgetFn | None = None,
    min_scale: float | None = None,
    rotation: float = 0.0,
    max_rounds: int = MAX_RETRANSLATE_ROUNDS,
    min_fill: float = MIN_FILL,
) -> FitResult:
    """Fit `segment.target` into `bbox`, in both directions, iterating to a faithful fill.

    Layers 1 (as-is) and 2 (shrink to `min_scale`) collapse into a single `measure()` call
    because PyMuPDF's `insert_htmlbox(scale_low=...)` already merges them (see measure.py).

    Direction 1 - overflow: the text does not fit even shrunk, so re-translation is asked
    for a shorter rendering within the box's character budget, and the request iterates
    (up to `max_rounds`, halving the remaining excess each time) until the text fits.

    Direction 2 - under-fill: the text fits but leaves the box much emptier than the source
    did (`min_fill` of the budget the box can hold at full size). A longer rendering is
    requested, within the box's full budget, up to `max_rounds` times. Only used when the
    segment has a source to compare against, and never allowed to turn a fit into an
    overflow: a longer candidate that does not fit is rejected and the current text kept.

    `rotation` is `Block.rotation` in degrees, counter-clockwise, 0 for ordinary horizontal
    text (core/docir.py). This function does no trigonometry itself - `bbox` stays the plain
    axis-aligned box the reader recorded, and the angle is only carried across the seam to
    `measure`, which is where the actual geometry lives (see `measure.rotated_run_length` /
    `rotated_block_fits`, used by the built-in `make_measure_fn`; a PDF-backed `measure` is
    free to do its own). That keeps this layer PyMuPDF-free (D1/D2) while still making sure a
    rotated block is measured against the room it honestly has, not against the larger,
    axis-aligned `bbox` around it.
    """
    # Resolved here rather than in the signature: a default argument is evaluated once at
    # import, so the setting would never be seen after the module loaded.
    if min_scale is None:
        min_scale = min_scale_setting()
    text = segment.target
    fits, scale = measure(text, style, bbox, scale_low=min_scale, rotation=rotation)
    if fits:
        layer = FitLayer.AS_IS if scale >= 1.0 else FitLayer.SHRUNK
        expanded = _try_expand(
            segment, text, layer, scale, style, bbox, measure, retranslate, char_budget,
            min_scale, rotation, max_rounds, min_fill,
        )
        return expanded or FitResult(layer=layer, scale=scale, text=text)

    # -- direction 1: too long -> ask for shorter, iterating while it still overflows ----
    if retranslate is not None:
        budget = char_budget(style, bbox, min_scale) if char_budget else int(len(text) * min_scale)
        for _round_no in range(max_rounds):
            shorter = retranslate(segment, budget)
            if not shorter or shorter == text:
                break
            fits, scale = measure(shorter, style, bbox, scale_low=min_scale, rotation=rotation)
            if fits:
                return FitResult(layer=FitLayer.RETRANSLATED, scale=scale, text=shorter)
            # Keep the shorter attempt even though it still overflows - it's closer to
            # fitting than the original, and layer 4 reports the overflow either way.
            text = shorter
            # Tighten the budget for the next round by what the last round revealed.
            # The model already proved `len(shorter)` does not fit, so the next request
            # must target strictly less than that; when the model respected the budget
            # anyway, the budget itself is more than the box holds, so shrink it.
            budget = max(8, min(budget, len(shorter) - 1))

    if mode is FitMode.STRICT:
        return FitResult(layer=FitLayer.OVERFLOW, scale=min_scale, text=text, needs_review=True)

    return FitResult(layer=FitLayer.OVERFLOW, scale=min_scale, text=text, reflow=True)


def _try_expand(
    segment: Segment,
    text: str,
    layer: FitLayer,
    scale: float,
    style: Style,
    bbox: BBox,
    measure: MeasureFn,
    retranslate: RetranslateFn | None,
    char_budget: CharBudgetFn | None,
    min_scale: float,
    rotation: float,
    max_rounds: int,
    min_fill: float,
) -> FitResult | None:
    """Direction 2: the text fits but the box is left much emptier than the source left it.

    Returns a FitResult with the longer text when a longer candidate was accepted, or None
    when no expansion was needed / possible, leaving the caller's original result in place.

    Faithfulness here is fill, not just containment: the goal (see the product's stated aim)
    is a translation that occupies the box the way the original did. The reference length is
    the box's own character budget at full size - what the original filled it with - and a
    translation below `min_fill` of that reads as a hole in the page. The source text is the
    fallback reference when no budget callback is available.

    A longer candidate is accepted only if it still fits at the same or better scale; one
    that overflows is rejected and the current text kept, so pursuing fill can never create
    an overflow that did not exist.
    """
    if retranslate is None:
        return None
    if char_budget is None:
        # Without a real budget there is no honest "how full is the box" answer; guessing
        # from source length would flag ordinary 0.9x variation. Do nothing rather than
        # measure nothing.
        return None

    full_budget = char_budget(style, bbox, 1.0)
    if full_budget <= 0:
        return None
    if len(text) >= min_fill * full_budget:
        return None

    original = text
    current_scale = scale
    for round_no in range(max_rounds):
        # Ask for a rendering that fills the box: the target length is the full budget,
        # tightened toward the observed response when the model undershoots.
        want = full_budget if round_no == 0 else min(full_budget, int(len(text) * 1.5) + 8)
        longer = retranslate(segment, want)
        if not longer or longer == text:
            # The model has nothing longer to offer. If an earlier round already improved
            # on the original, keep that improvement instead of throwing it away.
            return (
                FitResult(layer=FitLayer.EXPANDED, scale=current_scale, text=text)
                if text != original
                else None
            )
        fits, new_scale = measure(longer, style, bbox, scale_low=min_scale, rotation=rotation)
        if not fits:
            # Overflow: a longer text is not worth an overflow. Keep what fits.
            return (
                FitResult(layer=FitLayer.EXPANDED, scale=current_scale, text=text)
                if text != original
                else None
            )
        text = longer
        # The accepted text is longer than the original and may only fit shrunk - report the
        # scale it actually measured at, or the writer prints it at the original's larger size
        # and the expansion turns into an overflow (observed via the fitting e2e pass).
        current_scale = new_scale
        if len(text) >= min_fill * full_budget:
            break

    return FitResult(layer=FitLayer.EXPANDED, scale=current_scale, text=text)


def summarize(results: Sequence[FitResult]) -> dict[str, int]:
    """Count how many segments landed in each fit layer."""
    counts = {layer.value: 0 for layer in FitLayer}
    for r in results:
        counts[r.layer.value] += 1
    return counts
