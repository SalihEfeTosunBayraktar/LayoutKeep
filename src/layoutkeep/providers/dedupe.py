"""Text this document repeats is translated once, and every occurrence gets that translation.

WHY THIS EXISTS. A form, a textbook and a paper all repeat themselves - running headers, repeated
table labels, the same instruction on every page. Measured over the recorded held-out runs (11
documents, 5,700 translated segments): irs_p505 repeats 537 of its 2,144 segments (25%),
irs_i1040gi 252 of 737 (34%), arXiv 2609.19145 154 of 489 (31%), plos 139 of 468 (30%).

What those repeats cost is not only requests. The same source sent twice does not come back the
same: irs_p505 has **80 groups whose identical source text produced more than one translation**
(272 segments), and IRS Form 1040's instructions rendered "Married filing separately" three ways
in one document ("ayrı ayrı beyan eden", "evli ayrı ayrı beyan eden", "ayrı ayrı evli") and
"Head of household" two ("hane başkanı", "hanevi"). A translated form whose labels are worded
differently row to row is not smooth, however correct each row is on its own.

WHAT IT DOES. Wraps a provider: segments sharing the same text are collapsed to their first
occurrence before the request, and the reply is copied to all of them - so the occurrences cannot
disagree and the document costs fewer requests. The shared key ignores whitespace and case
("Need more information or forms?" and "need more information or forms?" are one text).

WHAT IT DOES NOT DO. A source shorter than `MIN_WORDS` is never shared. One or two words really do
translate differently in different sentences - measured on the same runs: "where" came back as
"nerede" and as "ner", "ours" as "biz" and as "bizim" - and collapsing those would spread the
wrong sense across a document to save nothing. Everything else about the wrapped provider is
unchanged: it still sees one segment per distinct text, and the caller still gets one segment per
input, in order, with the flags of the answer it came from.
"""

from __future__ import annotations

import dataclasses

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.core.repeats import share_key
from layoutkeep.providers.batching import BatchProgress, ProgressCallback


class DedupeProvider:
    """Asks the wrapped provider for each distinct text once, and answers every occurrence with it."""

    def __init__(self, inner: object, *, enabled: bool | None = None) -> None:
        self.inner = inner
        self.enabled = enabled
        #: Cumulative over the job, not per call: the repair passes call the provider again with a
        #: handful of segments, and a per-call figure would be overwritten by them - the run would
        #: report that nothing was shared after sharing hundreds of segments in the main pass.
        self.totals: dict[str, int] = {"shared": 0, "saved": 0}

    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        if not self._enabled():
            return self.inner.translate(segments, src_lang, tgt_lang, glossary, on_progress)

        keys = {seg.block_id: share_key(seg.source) for seg in segments}
        first: dict[str, Segment] = {}
        unique: list[Segment] = []
        skipped_chars = 0
        for seg in segments:
            key = keys[seg.block_id]
            if key is None:
                unique.append(seg)
            elif key in first:
                skipped_chars += len(seg.source)  # a repeat: answered from its first occurrence
            else:
                first[key] = seg
                unique.append(seg)
        saved = len(segments) - len(unique)
        self.totals["shared"] += len(first)
        self.totals["saved"] += saved
        if not saved:
            return self.inner.translate(segments, src_lang, tgt_lang, glossary, on_progress)

        answered = {
            seg.block_id: seg
            for seg in self._ask(
                unique, src_lang, tgt_lang, glossary, on_progress, saved, len(segments), skipped_chars
            )
        }
        out: list[Segment] = []
        for seg in segments:
            key = keys[seg.block_id]
            source_seg = first.get(key, seg) if key is not None else seg
            reply = answered.get(source_seg.block_id)
            out.append(seg if reply is None else _as(reply, seg))
        return out

    def _enabled(self) -> bool:
        if self.enabled is not None:
            return self.enabled
        return bool(tunables.get("translation.reuse_repeats"))

    def _ask(
        self,
        unique: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None,
        on_progress: ProgressCallback | None,
        saved: int,
        asked: int,
        skipped_chars: int,
    ):
        """Ask for the distinct texts, counting the ones answered from their own repeat."""
        if on_progress is None:
            return self.inner.translate(unique, src_lang, tgt_lang, glossary, None)

        total_chars = skipped_chars + sum(len(s.source) for s in unique)
        on_progress(
            BatchProgress(
                segments_done=saved,
                segments_total=asked,
                chars_done=skipped_chars,
                chars_total=total_chars,
                elapsed_s=0.0,
                batch_size=saved,
            )
        )

        def forward(progress: BatchProgress) -> None:
            on_progress(
                BatchProgress(
                    segments_done=saved + progress.segments_done,
                    segments_total=asked,
                    chars_done=skipped_chars + progress.chars_done,
                    chars_total=total_chars,
                    elapsed_s=progress.elapsed_s,
                    batch_size=progress.batch_size,
                )
            )

        return self.inner.translate(unique, src_lang, tgt_lang, glossary, forward)


def _as(reply: Segment, asked: Segment) -> Segment:
    """`reply` for `asked`: the answer's text and flags, the asker's own identity and context."""
    return dataclasses.replace(
        reply,
        block_id=asked.block_id,
        source=asked.source,
        context_before=asked.context_before,
        context_after=asked.context_after,
        max_len=asked.max_len,
    )
