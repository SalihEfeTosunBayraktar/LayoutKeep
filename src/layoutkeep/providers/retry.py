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
"""

from __future__ import annotations

import statistics
from typing import Protocol

from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import is_data_only
from layoutkeep.providers.batching import BatchTooLargeError
from layoutkeep.providers.passthrough import is_identical

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


def _is_runaway(segment: Segment, typical: float | None) -> bool:
    return (
        typical is not None
        and bool(segment.target)
        and len(segment.source) >= _RUNAWAY_MIN_SOURCE
        and len(segment.target) > _RUNAWAY_FACTOR * typical * len(segment.source)
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
    pending = [
        s for s in segments
        if (not s.target and not is_data_only(s.source))
        or is_identical(s)
        or _is_runaway(s, typical)
    ]
    if not pending:
        return 0

    try:
        answered = provider.translate(pending, **kwargs)
    except _RECOVERABLE:
        # This pass runs over a document that is already translated as well as it is going to
        # be; a server that dies now must not cost the work that succeeded before it.
        return 0

    filled = {
        seg.block_id: seg
        for seg in answered
        if seg.target and not is_identical(seg) and not _is_runaway(seg, typical)
    }
    recovered = 0
    by_id = {seg.block_id: seg for seg in pending}
    for block_id, reply in filled.items():
        segment = by_id.get(block_id)
        if segment is None:
            continue
        segment.target = reply.target
        recovered += 1
    return recovered
