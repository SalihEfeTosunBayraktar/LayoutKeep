"""Splits a list of segments into requests sized by content, not by a fixed segment count.

Why this exists: a single `/v1/chat/completions` call carrying an entire book (hundreds of
segments) either times out or never returns on a local model. Splitting by a fixed segment
count is no better - five short headings and five long paragraphs are very different amounts
of work for the model. So batches are built against a character budget instead (see
`core/estimate.py` for the token-estimate helpers this could later be swapped for).

This module is layout-blind like the rest of `providers/` (D2, see docs/CONTRACT.md): it only
knows `Segment`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment

#: Default character budget per request - mostly a safety net against one pathologically long
#: paragraph blowing out a request's latency, not the main lever (see `AdaptiveBatchSize`).
DEFAULT_BATCH_CHARS = 2000

#: Fixed segment-count cap used by `chunk_segments` when a caller wants a plain, non-adaptive
#: cap (its own tests, or a caller that wants "one segment per request" specifically). This is
#: no longer the default segment count `run_batches`/`OpenAICompatProvider` actually use in
#: practice - see `ADAPTIVE` and `AdaptiveBatchSize` for that. Kept because a per-model reliable
#: batch size varies roughly fivefold (measured 1 for a 9B model, 5 for gemma-4-e4b on a
#: correctly configured server - see `AdaptiveBatchSize`'s docstring), so no single constant is
#: the right answer for every model; a fixed 1 is only ever right as a starting point.
DEFAULT_MAX_SEGMENTS = 1

#: Sentinel for `run_batches`'/`OpenAICompatProvider`'s `max_segments` parameter meaning "size
#: the batch adaptively" (see `AdaptiveBatchSize`) instead of holding to a fixed cap. This is
#: the default for both; pass an int instead to pin a fixed size - the batch benchmark tool
#: wants reproducible timings, not a moving target, so it pins.
ADAPTIVE = "adaptive"

#: A request's total time is dominated by two very different things: the model's one-time cold
#: load (can be minutes on a large local model) and per-character generation time after that.
#: The first batch pays the load cost; later batches essentially don't, so they get a much
#: smaller base allowance.
FIRST_BATCH_BASE_TIMEOUT_S = 240.0
WARM_BATCH_BASE_TIMEOUT_S = 15.0

#: Fallback generation rate used only until a real batch's throughput has been measured.
#: Deliberately conservative (slow): a timeout that is too long just costs waiting, one that is
#: too short costs a failed batch that has to be retried.
DEFAULT_CHARS_PER_SECOND = 12.0

#: Clamp so a pathologically small or large batch can't produce a useless timeout (a few
#: seconds) or an unreasonable one (a multi-hour hang before the user sees an error).
MIN_BATCH_TIMEOUT_S = 30.0
MAX_BATCH_TIMEOUT_S = 900.0


class BatchTooLargeError(Exception):
    """Raised by a `translate_batch` callback to report a *protocol* failure - a reply that
    came back malformed, or with fewer entries than segments sent - as opposed to a *transport*
    failure (timeout, connection drop).

    The distinction matters to `run_batches`' adaptive sizing (`AdaptiveBatchSize`): a
    malformed/short reply is evidence the batch was too big for the model to hold together in
    one valid JSON array, so it should shrink. A network blip says nothing about that, and must
    not shrink anything - see `run_batches`.
    """


def _content_chars(seg: Segment) -> int:
    """Characters this segment actually adds to a request: its own text plus the context that
    travels with it (context is never translated, but the model still has to read it)."""
    return len(seg.source) + len(seg.context_before) + len(seg.context_after)


def _take_one_batch(
    segments: Sequence[Segment], start: int, max_chars: int, max_segments: int | None
) -> list[Segment]:
    """Greedily build one batch starting at `segments[start]`: keep adding segments while the
    running character total stays at or under `max_chars` and the count stays under
    `max_segments` (pass None to only budget by characters). A single segment larger than
    `max_chars` still gets its own batch rather than being split - segments are one document
    block each and splitting one would break the `block_id` round-trip the whole layer relies
    on.

    Shared by `chunk_segments` (which calls this in a loop to chunk a whole sequence up front)
    and `run_batches`' adaptive loop (which needs a fresh size for every single batch, so it
    cannot chunk everything up front).
    """
    batch: list[Segment] = []
    chars = 0
    for seg in segments[start:]:
        seg_chars = _content_chars(seg)
        over_chars = batch and chars + seg_chars > max_chars
        over_count = batch and max_segments is not None and len(batch) >= max_segments
        if over_chars or over_count:
            break
        batch.append(seg)
        chars += seg_chars
    return batch


def chunk_segments(
    segments: Sequence[Segment],
    max_chars: int,
    max_segments: int | None = DEFAULT_MAX_SEGMENTS,
) -> list[list[Segment]]:
    """Group `segments` into batches whose total content stays under `max_chars` and whose
    count stays at or under `max_segments` (pass None to only budget by characters).

    `max_segments=1` (the default) means every batch is a single segment. This is a plain,
    fixed-size chunker; `run_batches` uses adaptive sizing instead by default (see `ADAPTIVE`),
    but this function stays a simple, predictable building block for callers (and tests) that
    want one specific fixed cap.
    """
    batches: list[list[Segment]] = []
    start = 0
    while start < len(segments):
        batch = _take_one_batch(segments, start, max_chars, max_segments)
        batches.append(batch)
        start += len(batch)
    return batches


def batch_timeout(
    chars: int,
    *,
    is_first: bool,
    chars_per_second: float | None,
    first_batch_base: float = FIRST_BATCH_BASE_TIMEOUT_S,
) -> float:
    """Adaptive per-batch timeout: a base allowance (mostly model load) plus generation time
    estimated from how much text is actually in this batch, using the best rate known so far -
    a real measurement once one exists, a conservative guess before that.

    `first_batch_base` defaults to the module constant (240s), sized for a cold local model
    that hasn't loaded yet. A caller whose server already has the model warm can pass a lower
    value instead of waiting out a base that no longer applies to them.
    """
    # Read now, not at import: a cold-load allowance is genuinely machine-dependent and the
    # user may have just changed it in the settings dialog. An explicit argument still wins.
    base = (
        first_batch_base
        if is_first
        else tunables.get("timeout.warm_batch_s")
    )
    rate = chars_per_second or DEFAULT_CHARS_PER_SECOND
    estimate = base + chars / rate
    return max(MIN_BATCH_TIMEOUT_S, min(MAX_BATCH_TIMEOUT_S, estimate))


#: Where an adaptive run starts - conservative on purpose, see `AdaptiveBatchSize`.
DEFAULT_ADAPTIVE_START_SEGMENTS = 1

#: Ceiling on how large an adaptive batch may grow to, regardless of how long its winning
#: streak is. Without this, a very capable model would keep growing indefinitely, until one bad
#: reply loses a batch large enough to be a real setback instead of a shrug (and takes minutes
#: to redo). 20 is comfortably above every measured reliable size to date (5 for gemma-4-e4b on
#: a correctly configured server) while still bounding the worst case.
DEFAULT_ADAPTIVE_MAX_SEGMENTS = 20


class AdaptiveBatchSize:
    """How many segments go in the next request, tuned live against what the model actually
    holds together in one valid reply.

    Measured evidence motivating this (gemma-4-e4b, 8192 context, single slot, full GPU
    offload, same passage from pg11.epub each time)::

        size 1 -> 1/1 in 32.7s      size 4 -> 4/4 in 44.7s
        size 2 -> 2/2 in 37.3s      size 5 -> 5/5 in 60.1s
        size 3 -> 3/3 in 42.2s      size 6 -> 3/6 in 341s   <- breaks here

    Cost is dominated by per-request overhead, not segment count (size 5 is ~2.7x more
    efficient per segment than size 1), but the reliable ceiling itself varies roughly fivefold
    between models (a 9B model tested elsewhere only ever held size 1 together). Neither "always
    1" nor any other single constant is right for every model - so the size is discovered per
    run instead of configured.

    Starts conservative (`start`) and grows by one segment after every batch that comes back
    fully parseable (`record_success`). The moment a batch fails to parse or comes back short
    (see `BatchTooLargeError`), that size becomes a permanent ceiling (`record_failure`):
    `current` is pulled back below it and never grows that high again, so the run cannot
    oscillate between trying and re-failing the same size.
    """

    def __init__(
        self,
        start: int = DEFAULT_ADAPTIVE_START_SEGMENTS,
        max_size: int | None = None,
    ) -> None:
        self.current = start
        # None means "whatever the tunable says right now", so the ceiling can be
        # changed between jobs without restarting.
        self._max = (
            tunables.get("batch.adaptive_max_segments") if max_size is None else max_size
        )
        #: Smallest size known to fail so far, or None if nothing has failed yet. `current`
        #: must always stay strictly below this.
        self._ceiling: int | None = None

    def record_success(self) -> None:
        grown = self.current + 1
        if grown > self._max:
            return
        if self._ceiling is not None and grown >= self._ceiling:
            return
        self.current = grown

    def record_failure(self, failed_size: int) -> None:
        self._ceiling = failed_size if self._ceiling is None else min(self._ceiling, failed_size)
        self.current = max(1, min(self.current, self._ceiling - 1))


@dataclass(slots=True)
class BatchProgress:
    """Reported after each batch so a caller (CLI or GUI) can show progress."""

    segments_done: int
    segments_total: int
    chars_done: int
    chars_total: int
    elapsed_s: float
    #: How many segments the batch just completed actually carried. This is the size the run is
    #: currently settled on - the cap in effect (fixed, or `AdaptiveBatchSize.current` when
    #: sizing adaptively) except for a trailing batch that got fewer segments only because the
    #: input ran out. Lets a caller (CLI/GUI) show what size the run has settled on.
    batch_size: int = 1


ProgressCallback = Callable[[BatchProgress], None]


def run_batches(
    segments: Sequence[Segment],
    max_chars: int,
    translate_batch: Callable[[list[Segment]], list[Segment]],
    on_progress: ProgressCallback | None = None,
    max_segments: int | str | None = ADAPTIVE,
) -> list[Segment]:
    """Drive `translate_batch` over `segments` split into content-sized batches.

    `translate_batch` must return one Segment per segment it was given, `block_id` unchanged
    (the same contract `TranslationProvider.translate` promises overall).

    `max_segments` controls how batches are sized:
      - `ADAPTIVE` (the default): start small and grow while replies come back valid, shrink
        (permanently, as a ceiling) the moment one does not - see `AdaptiveBatchSize`. A batch
        that fails with `BatchTooLargeError` is retried at the new, smaller size before giving
        up on its segments - a protocol failure becomes a slowdown, not a lost batch.
      - an `int`: a fixed cap, never adjusted. For a caller that wants reproducible batch sizes
        (the benchmark tool) or that already knows a safe size for its model.
      - `None`: no count cap at all, only the character budget applies.

    A batch that raises after at least one earlier batch has already succeeded is caught here:
    its segments come back with `needs_review=True` instead of losing the whole job (this is
    the property that matters most - a server that only chokes on one big paragraph should not
    cost the book that translated fine around it). But if the very first batch raises - nothing
    has been salvaged yet, so there is no partial progress to protect - the exception is left to
    propagate, matching what callers (cli.py, the GUI worker) already handle: a dead or
    unreachable server is reported once, clearly, instead of being retried batch after batch
    until every one of them has separately timed out. This applies the same way whether the
    batch raised `BatchTooLargeError` at the smallest possible size (1 segment - nothing left to
    shrink to) or any other exception (a transport failure never shrinks anything, see above).
    """
    if not segments:
        return []

    adaptive = max_segments == ADAPTIVE
    size = AdaptiveBatchSize() if adaptive else None
    fixed_cap: int | None = None if adaptive else max_segments  # type: ignore[assignment]

    chars_total = sum(_content_chars(s) for s in segments)
    segments_total = len(segments)

    results: list[Segment] = []
    segments_done = 0
    chars_done = 0
    run_started = time.monotonic()
    any_success = False

    offset = 0
    while offset < len(segments):
        cap = size.current if size is not None else fixed_cap
        batch = _take_one_batch(segments, offset, max_chars, cap)

        try:
            batch_result = translate_batch(batch)
        except BatchTooLargeError:
            if size is not None and len(batch) > 1:
                # Evidence the batch itself was too big, not that the model/server is down -
                # shrink and retry the same segments rather than spend them on needs_review.
                size.record_failure(len(batch))
                continue
            # Can't shrink any further (fixed cap, uncapped, or already down to one segment):
            # nothing left to try smaller, so this behaves like any other batch failure.
            if not any_success:
                raise
            batch_result = [_review_copy(seg) for seg in batch]
        except Exception:  # see docstring: only swallowed once something is already saved
            if not any_success:
                raise
            batch_result = [_review_copy(seg) for seg in batch]
        else:
            any_success = True
            if size is not None:
                size.record_success()

        results.extend(batch_result)
        segments_done += len(batch)
        chars_done += sum(_content_chars(s) for s in batch)
        offset += len(batch)

        if on_progress is not None:
            on_progress(
                BatchProgress(
                    segments_done=segments_done,
                    segments_total=segments_total,
                    chars_done=chars_done,
                    chars_total=chars_total,
                    elapsed_s=time.monotonic() - run_started,
                    batch_size=len(batch),
                )
            )

    return results


def _review_copy(seg: Segment) -> Segment:
    """What a segment becomes when its whole batch failed to translate: flagged, not dropped,
    never filled with the source text."""
    return Segment(
        block_id=seg.block_id,
        source=seg.source,
        target="",
        context_before=seg.context_before,
        context_after=seg.context_after,
        max_len=seg.max_len,
        confidence=seg.confidence,
        needs_review=True,
        # K1: sebepsiz needs_review editor'de aciklamasiz kalir / review must say why
        review_reason="partinin tamamı çevrilemedi / whole batch failed to translate",
        from_memory=False,
    )
