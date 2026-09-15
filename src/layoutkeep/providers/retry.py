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

from typing import Protocol

from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import is_data_only
from layoutkeep.providers.batching import BatchTooLargeError

#: What a provider can fail with here that this pass should absorb rather than propagate: the
#: transport (`OSError`, and `TimeoutError` which is one), a reply that would not parse
#: (`ValueError`), and a batch the server rejects outright. Anything else is a defect in the
#: pipeline, not a flaky server, and must not be hidden behind "we tried".
_RECOVERABLE = (OSError, TimeoutError, ValueError, BatchTooLargeError)


class _Provider(Protocol):
    def translate(self, segments: list[Segment], **kwargs: object) -> list[Segment]: ...


def retry_untranslated(provider: _Provider, segments: list[Segment], **kwargs: object) -> int:
    """Resend the segments with no target, filling in the ones that come back. Returns how many
    were recovered.

    `segments` is updated in place, so the caller's list (and the document written from it) sees
    the recovered text without any re-merging.
    """
    pending = [s for s in segments if not s.target and not is_data_only(s.source)]
    if not pending:
        return 0

    try:
        answered = provider.translate(pending, **kwargs)
    except _RECOVERABLE:
        # This pass runs over a document that is already translated as well as it is going to
        # be; a server that dies now must not cost the work that succeeded before it.
        return 0

    filled = {seg.block_id: seg.target for seg in answered if seg.target}
    recovered = 0
    by_id = {seg.block_id: seg for seg in pending}
    for block_id, target in filled.items():
        segment = by_id.get(block_id)
        if segment is None or segment.target:
            continue
        segment.target = target
        recovered += 1
    return recovered
