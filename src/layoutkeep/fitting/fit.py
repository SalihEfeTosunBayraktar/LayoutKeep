"""Three-layer fit strategy (docs/CONTRACT.md D3): shrink, then re-translate shorter, then
accept overflow or reflow. Try each layer in order and stop at the first success.

`fitting/` triggers a re-translation request but never calls a translation provider itself
(D2) - callers pass a `RetranslateFn` that wires this to the real provider.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from layoutkeep.core.copies import drops_numbers, is_copy, is_identical
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
    #: The engine's own explanation for a flag, when it knows more than "did not fit". The
    #: front-ends show this instead of their generic sentence: measured on the book, most flags
    #: are not text that could not be shortened but a box the fitting had to crush to stay off
    #: the next block (`room_below` can take it to 6pt, and nothing fits in 6pt), and telling a
    #: user "shrinking was not enough" when the box is the problem sends them to the wrong knob.
    review_reason: str = ""
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

#: A fit that only holds because the type was shrunk this far is a fit the box did not really
#: have. Measured on arXiv 2507.03009 page 5 (gemma-4-e4b): 42 of 70 blocks fitted only shrunk -
#: 23 of them prose at 9.4pt in a 220pt column, from 517 to 1138 characters of source - and the
#: shrink direction is where they stayed, because `measure` said "fits" and nothing ever asked
#: for a rendering that fits at full size. A translation that needs 15% less type is a
#: translation that wants fewer words.
HEAVY_SHRINK = 0.95
_HEAVY_SHRINK_KEY = "fit.shorten_below_scale"

#: Below this many characters a text is too short to compress usefully. The ladder spent 14
#: requests on that same table page asking "Ücretli" (7 characters) for 4 and "✓" (1) for 2 -
#: targets no reply can meet, so each one burned a round trip and risked replacing a correct
#: translation with a worse one.
_MIN_SHORTEN_CHARS = 24

#: A target at or above this share of the current text is not worth asking for: the model would
#: have to cut almost nothing, and a re-rendering of the same length is a different translation
#: with no gain.
_SHORTEN_HEADROOM = 0.95

#: How many attempts the "fits only shrunk" case gets. Two, not `MAX_RETRANSLATE_ROUNDS`: one
#: request usually overshoots the budget and the second lands inside it, while a third would
#: triple the request count of every shrunk block on a dense page - and a shrunk block is
#: already readable, so the prize is smaller than on an overflow.
_SHRUNK_ATTEMPTS = 2


def heavy_shrink_setting() -> float:
    """The scale below which a fit counts as "only held by shrinking", as set right now."""
    from layoutkeep.core import tunables

    return float(tunables.get(_HEAVY_SHRINK_KEY))

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
    text = even_leaders(segment.source, segment.target)
    fits, scale = measure(text, style, bbox, scale_low=min_scale, rotation=rotation)
    if fits:
        # A fit that only holds because the type was shrunk hard is a fit the box did not have;
        # a shorter rendering that fits at full size is the better answer (see HEAVY_SHRINK).
        if scale < heavy_shrink_setting():
            shortened = _try_shorten(segment, text, scale, style, bbox, measure, retranslate,
                                     char_budget, min_scale, rotation)
            if shortened is not None:
                return shortened
        layer = FitLayer.AS_IS if scale >= 1.0 else FitLayer.SHRUNK
        expanded = _try_expand(
            segment, text, layer, scale, style, bbox, measure, retranslate, char_budget,
            min_scale, rotation, max_rounds, min_fill,
        )
        return expanded or FitResult(layer=layer, scale=scale, text=text)

    # -- direction 1: too long -> ask for shorter, iterating while it still overflows ----
    if retranslate is not None:
        budget = char_budget(style, bbox, min_scale) if char_budget else int(len(text) * min_scale)
        # The box's own budget is an average-advance estimate and can over-state what fits (the
        # text in hand is proof: it does not fit at `min_scale`). When it does, the target is
        # taken from that proof instead, so the request always asks for strictly less than the
        # text that just failed - asking to keep the same length buys nothing.
        budget = min(budget, max(_MIN_SHORTEN_CHARS, int(len(text) * min_scale)))
        for _round_no in range(max_rounds):
            # A text too short to compress has no shorter form worth a request: the table page's
            # "Ücretli" (7 characters) was asked for 4, three rounds over, and "✓" (1) for 2.
            if len(text) < _MIN_SHORTEN_CHARS or budget >= len(text):
                break
            shorter = retranslate(segment, budget)
            if not shorter or shorter == text or _is_source(segment, shorter):
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


#: A run of this many dots or more is a leader - the fill between a contents entry and its page
#: number - not an ellipsis.
_LEADER = re.compile(r"(?:\.\s?){4,}\.?|…{2,}|(?:·\s?){4,}")
_MARKERS = re.compile(r"</?\d+>")


def even_leaders(source: str, target: str) -> str:
    """Resize the translation's leader so the line keeps the source's length.

    Leader dots fill a contents line to the column's edge. A translation that keeps the source's
    dots runs longer or shorter by exactly the difference in wording, so every entry overflowed
    by its own amount and was shrunk to its own size - 9.3pt to 12pt down one NIST contents page.
    With the fill resized, entries fit alike. At least three dots are kept, so a leader never
    disappears.
    """
    if not _LEADER.search(_MARKERS.sub("", source)):
        return target
    match = _LEADER.search(target)
    if match is None:
        return target
    without = len(_MARKERS.sub("", target)) - len(match.group(0))
    wanted = max(3, len(_MARKERS.sub("", source)) - without)
    padding = " " if match.group(0).endswith(" ") else ""
    return target[: match.start()] + "." * (wanted - len(padding)) + padding + target[match.end():]


def _is_source(segment: Segment, reply: str) -> bool:
    """True when a re-rendering is the source handed back rather than a translation.

    A model asked for a shorter version sometimes returns the source, and for a language that
    runs longer than English the source is exactly the shorter text that fits - so it was
    accepted as a successful retranslation and replaced a correct translation (book page 61).
    Judged by `core.copies.is_copy`, which ignores inline markers the reply may have dropped.
    """
    return bool(segment.source) and (
        is_identical(segment.source, reply)
        or is_copy(segment.source, reply)
        # A re-rendering that loses a number the source has is not the same translation made
        # shorter; it is a different text (NIST glossary: "CNSSI 4009" came back as "CNSS").
        or drops_numbers(segment.source, reply)
    )


def _try_shorten(
    segment: Segment,
    text: str,
    scale: float,
    style: Style,
    bbox: BBox,
    measure: MeasureFn,
    retranslate: RetranslateFn | None,
    char_budget: CharBudgetFn | None,
    min_scale: float,
    rotation: float,
) -> FitResult | None:
    """The text fits, but only because the type was shrunk hard: ask for one that fits at full size.

    Returns a `RETRANSLATED` result when a shorter rendering fits at a better scale than the
    current one, else None and the caller keeps its shrunk fit.

    Two properties matter. The candidate must fit at a scale better than what we already have -
    a shorter text that still needs the same shrink is not an improvement, and a shorter text
    that only fits shrunk *more* would be a regression. And the candidate must not lose the
    source's numbers, for the same reason the overflow direction refuses one: a compression that
    drops a figure is a different text, not the same text made shorter.

    Only the shrink case reaches this. An overflow has its own ladder above, and the two never
    run for the same segment.
    """
    if retranslate is None or char_budget is None:
        return None
    if len(text) < _MIN_SHORTEN_CHARS:
        return None

    budget = char_budget(style, bbox, 1.0)
    if budget <= 0 or budget >= _SHORTEN_HEADROOM * len(text):
        return None

    for _round_no in range(_SHRUNK_ATTEMPTS):
        shorter = retranslate(segment, budget)
        if not shorter or shorter == text or _is_source(segment, shorter):
            return None
        fits, new_scale = measure(shorter, style, bbox, scale_low=min_scale, rotation=rotation)
        if fits and new_scale > scale:
            return FitResult(layer=FitLayer.RETRANSLATED, scale=new_scale, text=shorter)
        # Not an improvement: the reply was still too long for the box at full size. Target
        # strictly less than what it actually produced, which is the only thing we learned.
        budget = max(_MIN_SHORTEN_CHARS, min(budget, len(shorter) - 1))
        if budget >= _SHORTEN_HEADROOM * len(text):
            return None
    return None


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
        if not longer or longer == text or _is_source(segment, longer):
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
