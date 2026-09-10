"""Deterministic, network-free provider for tests.

Lets a test pick, per segment id, which failure mode to exercise: normal translation, a
malformed model reply, or the model refusing to translate that segment.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Segment
from layoutkeep.providers.batching import BatchProgress, ProgressCallback

#: Same marker syntax DocIR wraps inline-styled runs in. Opaque to this layer (D2) - only
#: used here to simulate a model that silently drops them from its reply.
_MARKER_RE = re.compile(r"<(/?)(\d+)>")


class FakeProvider:
    """Test double for TranslationProvider. No network, fully deterministic.

    Args:
        translations: block_id -> target text to return for a normal translation.
            Segments whose id is not present fall back to f"[{tgt_lang}] {source}".
        malformed_ids: ids that simulate the model returning unparsable JSON for that
            segment. Returned with empty target and needs_review=True.
        refuse_ids: ids that simulate the model declining to translate that segment
            (e.g. refusal text, empty choice). Returned with empty target and
            needs_review=True.
        drop_marker_ids: ids that simulate a model reply that looks fine but silently
            strips the `<N>`/`</N>` inline-style markers from the translated text.
            Returned with needs_review=False, same as a real "confident but wrong" reply -
            the caller (or core, once markers are applied back to spans) is what should
            catch this, not FakeProvider.
    """

    def __init__(
        self,
        translations: dict[str, str] | None = None,
        malformed_ids: set[str] | None = None,
        refuse_ids: set[str] | None = None,
        drop_marker_ids: set[str] | None = None,
    ) -> None:
        self.translations = translations or {}
        self.malformed_ids = malformed_ids or set()
        self.refuse_ids = refuse_ids or set()
        self.drop_marker_ids = drop_marker_ids or set()

    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        results: list[Segment] = []
        for seg in segments:
            if seg.block_id in self.malformed_ids or seg.block_id in self.refuse_ids:
                results.append(
                    Segment(
                        block_id=seg.block_id,
                        source=seg.source,
                        target="",
                        context_before=seg.context_before,
                        context_after=seg.context_after,
                        max_len=seg.max_len,
                        confidence=seg.confidence,
                        needs_review=True,
                        from_memory=False,
                    )
                )
                continue
            target = self.translations.get(seg.block_id, f"[{tgt_lang}] {seg.source}")
            if seg.block_id in self.drop_marker_ids:
                target = _MARKER_RE.sub("", target)
            results.append(
                Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    target=target,
                    context_before=seg.context_before,
                    context_after=seg.context_after,
                    max_len=seg.max_len,
                    confidence=seg.confidence,
                    needs_review=False,
                    from_memory=False,
                )
            )
        if on_progress is not None and results:
            chars = sum(len(s.source) for s in segments)
            on_progress(
                BatchProgress(
                    segments_done=len(results),
                    segments_total=len(segments),
                    chars_done=chars,
                    chars_total=chars,
                    elapsed_s=0.01,
                    batch_size=len(results),
                )
            )
        return results
