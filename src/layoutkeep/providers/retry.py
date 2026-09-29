"""One more attempt at the segments whose reply never arrived.

`batching.run_batches` retries a batch that *raises*: `BatchTooLargeError` shrinks it and sends
the same segments again, so a protocol failure costs time instead of text. It cannot see the
failure that actually lost text on `computer-systems-Architecture.pdf` - the request succeeded,
the reply came back, and some segments in it had no translation attached. Nothing raised, so
nothing was retried, and every one of those blocks kept its source text in the output document.

Measured there: 17 of 210 segments, and with them a quarter of the prose on the page.

A lost segment is almost always a reply the parser could not line up with the batch it answered,
not text the model refuses to translate - so asking again, in the much smaller batch the leftovers
make, recovers most of them. Exactly one extra pass: a segment the model genuinely will not
translate must not hold the job open, and `passthrough.flag_untranslated` is there to report
whatever is still missing afterwards.

What survives even that is a whole paragraph, and the last resort cuts it: `providers/split.py`
asks for its sentences and list items one at a time. The ladder above changes the request's
company and context; this changes its size, which is what the echoes respond to.
"""

from __future__ import annotations

import dataclasses
import statistics
import sys
from typing import Protocol

from layoutkeep.core import tunables
from layoutkeep.core.copies import drops_numbers, garbled_words, ordinary_words, wrong_language
from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import is_data_only
from layoutkeep.providers.batching import BatchTooLargeError
from layoutkeep.providers.passthrough import is_copy_of_source, is_identical
from layoutkeep.providers.split import pieces, reassemble

#: What a provider can fail with here that this pass should absorb rather than propagate: the
#: transport (`OSError`, and `TimeoutError` which is one), a reply that would not parse
#: (`ValueError`), and a batch the server rejects outright. Anything else is a defect in the
#: pipeline, not a flaky server, and must not be hidden behind "we tried".
_RECOVERABLE = (OSError, TimeoutError, ValueError, BatchTooLargeError)


#: A reply this many times longer, relative to its source, than this job's replies typically
#: are is not a translation of that source. Book page 61: a caption came back with sentences of
#: the neighbouring paragraph (sent as context) appended - about six times its source, where the
#: page's other replies ran near 1.2. Relative to the job's own median, so a language pair that
#: normally expands or contracts sets its own scale.
_RUNAWAY_FACTOR = 2.0

#: Below this many source characters the ratio means nothing: "Read" -> "Okuma" is 25% longer.
_RUNAWAY_MIN_SOURCE = 20


def _typical_ratio(segments: list[Segment]) -> float | None:
    ratios = [
        len(s.target) / len(s.source)
        for s in segments
        if s.target and len(s.source) >= _RUNAWAY_MIN_SOURCE and not is_identical(s)
    ]
    return statistics.median(ratios) if len(ratios) >= 3 else None


def _is_runaway(source: str, target: str, typical: float | None) -> bool:
    return (
        typical is not None
        and bool(target)
        and len(source) >= _RUNAWAY_MIN_SOURCE
        and len(target) > _RUNAWAY_FACTOR * typical * len(source)
    )


def _accepted(segment: Segment, typical: float | None, target_lang: str) -> bool:
    """Would this reply count as a translation of that source?

    One definition, used by the batch ask and by the piece-by-piece last resort, so a text
    assembled from pieces is held to exactly the standard a single reply is.
    """
    return (
        bool(segment.target)
        and not is_identical(segment)
        and not is_copy_of_source(segment)
        and not _is_runaway(segment.source, segment.target, typical)
        and not drops_numbers(segment.source, segment.target, target_lang)
        and wrong_language(segment.target, target_lang) is None
        and not garbled_words(segment.source, segment.target)
    )


class _Provider(Protocol):
    def translate(self, segments: list[Segment], **kwargs: object) -> list[Segment]: ...


def retry_untranslated(provider: _Provider, segments: list[Segment], **kwargs: object) -> int:
    """Resend the segments with no target, or whose target is the source handed straight back,
    filling in the ones that come back translated. Returns how many were recovered.

    An echo is retried because it is intermittent: three translations of the same ten book pages
    each left a different paragraph in English. So is a reply that ran on past its source (see
    `_RUNAWAY_FACTOR`). A retry that fails the same way keeps the first reply, and
    `flag_passthrough` still reports an echo.

    `segments` is updated in place, so the caller's list (and the document written from it) sees
    the recovered text without any re-merging.
    """
    typical = _typical_ratio(segments)
    target_lang = str(kwargs.get("tgt_lang") or "")
    pending = [
        s for s in segments
        if (not s.target and not is_data_only(s.source))
        or is_identical(s)
        or is_copy_of_source(s)
        or _is_runaway(s.source, s.target, typical)
        or (bool(s.target) and drops_numbers(s.source, s.target, target_lang))
        or (bool(s.target) and wrong_language(s.target, target_lang) is not None)
        or (bool(s.target) and bool(garbled_words(s.source, s.target)))
    ]
    if not pending:
        return 0

    # Sent WITHOUT the neighbouring-paragraph context. Measured on gemma-4-e4b: four exercise
    # items came back in English 3 times out of 3 with their context and translated 3 times out of
    # 3 without it (docs/campaign/JOURNAL.md, echo experiment) - resending the identical request
    # cannot recover them. The caller's segments keep their context.
    accepted = _ask(provider, pending, typical, kwargs)
    # Whatever still fails is asked for one segment at a time, a few times. A Time Machine
    # dialogue paragraph echoed in the main pass and in the batch retry, yet translated 24 times
    # out of 24 in isolation; a Think Python exercise echoed through three whole repair rounds and
    # translated when sent by hand. Under a loaded server the echo is not reproducible, so one more
    # attempt is not enough.
    for _attempt in range(_LONE_ATTEMPTS):
        still = [s for s in pending if s.block_id not in accepted]
        if not still:
            break
        for segment in still:
            accepted.update(_ask(_for_numbers(provider, segment), [segment], typical, kwargs))

    # What survived all of that is asked for in pieces (see `providers/split.py`). Only the
    # segments still failing, so a document that translated cleanly pays nothing for this.
    for segment in [s for s in pending if s.block_id not in accepted]:
        assembled = _ask_piecewise(provider, segment, typical, kwargs)
        if assembled:
            accepted[segment.block_id] = assembled

    mended = 0
    for segment in pending:
        if segment.block_id in accepted:
            segment.target = accepted[segment.block_id]
            mended += 1
        elif (
            segment.target
            and not ordinary_words(segment.source)
            and drops_numbers(segment.source, segment.target, target_lang)
        ):
            # A name, a code or a label whose every reply lost its figures keeps the source. Held-out
            # arXiv 2609.19113: the table cell "GLM-5.3" came back as the next cell's question,
            # translated, and each retry answered "GLM-5.3" - rightly, and rejected as an echo.
            segment.target = segment.source
            mended += 1
    return mended


#: How many times a segment that still fails is asked for on its own.
_LONE_ATTEMPTS = 3


def _for_numbers(provider: _Provider, segment: Segment) -> _Provider:
    """The provider to ask, for one segment on its last attempt.

    A reply that lost a number is asked for without the protection layer when there is one: the
    protection holds numbers back as placeholders, and on NIST's glossary the model dropped the
    placeholder for "(1)" 6 times out of 6 while keeping the plain "(1)" 3 times out of 3.
    """
    inner = getattr(provider, "inner", None)
    if inner is not None and segment.target and drops_numbers(segment.source, segment.target):
        return inner
    return provider


def _ask_piecewise(
    provider: _Provider, segment: Segment, typical: float | None, kwargs: dict
) -> str | None:
    """Ask for the segment in pieces, and put the replies back in the source's own separators.

    None when cutting would not help, when any piece came back unusable, or when the assembled
    text does not stand up as a translation of the whole - a half-translated paragraph is worse
    than an untranslated one, because it no longer reads as a loss.
    """
    cut = pieces(segment.source, max_pieces=int(tunables.get("translation.piecewise_max_pieces")))
    if not cut:
        return None
    target_lang = str(kwargs.get("tgt_lang") or "")
    replies: list[str] = []
    for piece in cut:
        # One piece at a time, always without context: the context is what the echo experiments
        # showed keeps a whole paragraph in English, and a piece does not need it to be translated.
        probe = dataclasses.replace(
            segment, source=piece.text, target="", context_before="", context_after=""
        )
        reply = _ask(provider, [probe], typical, kwargs).get(segment.block_id)
        if not reply:
            return None
        replies.append(reply)
    assembled = reassemble(replies, cut)
    whole = dataclasses.replace(segment, target=assembled)
    return assembled if _accepted(whole, typical, target_lang) else None


def _ask(
    provider: _Provider, batch: list[Segment], typical: float | None, kwargs: dict
) -> dict[str, str]:
    """Translate `batch` without context; return the replies that are real translations."""
    try:
        answered = provider.translate(
            [dataclasses.replace(s, context_before="", context_after="") for s in batch],
            **kwargs,
        )
    except _RECOVERABLE as exc:
        # This pass runs over a document that is already translated as well as it is going to
        # be; a server that dies now must not cost the work that succeeded before it. Said out
        # loud, though: a NIST paragraph stayed English after a retry that left no trace, and
        # without this line there was no way to tell a failed request from a refused one.
        print(
            f"retry     request for {len(batch)} segment(s) failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return {}
    wanted = {s.block_id for s in batch}
    target_lang = str(kwargs.get("tgt_lang") or "")
    return {
        seg.block_id: seg.target
        for seg in answered
        if seg.block_id in wanted and _accepted(seg, typical, target_lang)
    }
