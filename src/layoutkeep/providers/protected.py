"""Wraps any TranslationProvider so that literal values never reach the model.

`core/protect.py` has the patterns and the round-trip; this is what makes them take effect.
Without this decorator the module is inert, and a torque figure, a form number or a diagram
callout is handed to a translation model like any other run of text.

Two separate defences, because the failure modes differ:

  * A segment that is *nothing but* data - `is_data_only` - is never sent at all. A US tax form
    read through this pipeline produced 29 such segments, each one a request spent inviting a
    model to "improve" a number. Its translation is itself.
  * A segment that *contains* data still has to be translated, so each literal is swapped for a
    token first and put back from the source afterwards. What the model never sees, it cannot
    paraphrase.

A literal that does not come back is not repaired and not hidden: the value is simply missing
from that translation, and the segment is flagged for review.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import Protection, is_data_only, protect, restore
from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.batching import ProgressCallback


class ProtectedProvider(TranslationProvider):
    """Literal-preserving decorator around another TranslationProvider."""

    def __init__(self, inner: TranslationProvider) -> None:
        self.inner = inner
        #: Set by the last translate() call, for the CLI to report: how many literals were held
        #: back, how many segments were answered without a request, and how many literals the
        #: model failed to return.
        self.last_stats = {"protected": 0, "skipped": 0, "lost": 0}

    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        stats = {"protected": 0, "skipped": 0, "lost": 0}
        answered: dict[str, Segment] = {}
        to_send: list[Segment] = []
        protections: dict[str, Protection] = {}

        for seg in segments:
            if is_data_only(seg.source):
                seg.target = seg.source
                answered[seg.block_id] = seg
                stats["skipped"] += 1
                continue
            protection = protect(seg.source)
            if protection.count:
                protections[seg.block_id] = protection
                stats["protected"] += protection.count
            to_send.append(
                Segment(
                    block_id=seg.block_id,
                    source=protection.text,
                    context_before=seg.context_before,
                    context_after=seg.context_after,
                    max_len=seg.max_len,
                )
            )

        if to_send:
            # `on_progress` is forwarded only when the caller actually supplied one: several
            # providers (FakeProvider, CachedProvider) predate that parameter and do not accept
            # it, so passing None through would break every one of them.
            extra = {} if on_progress is None else {"on_progress": on_progress}
            for result in self.inner.translate(
                to_send, src_lang, tgt_lang, glossary, **extra
            ):
                answered[result.block_id] = result

        out: list[Segment] = []
        for seg in segments:
            result = answered.get(seg.block_id)
            if result is None:
                # The inner provider dropped a segment, which it is contractually not allowed to
                # do. Return the original flagged rather than silently shortening the list.
                seg.needs_review = True
                seg.review_reason = "sağlayıcı bu segmenti yanıtlamadı"
                out.append(seg)
                continue
            protection = protections.get(seg.block_id)
            if protection is not None and result.target:
                result.target, lost = restore(result.target, protection)
                if lost:
                    stats["lost"] += lost
                    result.needs_review = True
                    result.review_reason = (
                        f"{lost} korunan değer çeviride yok (ölçü, parça no veya referans)"
                    )
            # The wrapped provider translated a tokenised source; the caller must see the real
            # one. The reader's own verdict has to come back too - a segment the reader had
            # already flagged (mirrored text, a shaky OCR line) arrives here as a fresh Segment
            # built for the request, and returning that one unchanged would drop the flag and
            # the confidence with it.
            result.source = seg.source
            result.confidence = min(result.confidence, seg.confidence)
            if seg.needs_review:
                result.needs_review = True
                result.review_reason = result.review_reason or seg.review_reason
            out.append(result)

        self.last_stats = stats
        return out
