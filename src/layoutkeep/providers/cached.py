"""Wraps any TranslationProvider with a translation-memory cache.

Checks the memory first; only cache misses go to the wrapped provider. Fresh results are
stored back so the next run (or the next repeated header/footer in the same run) is free.
Results are always returned in the same order as the input segments.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.batching import BatchProgress, ProgressCallback
from layoutkeep.providers.memory import TranslationMemory


class CachedProvider(TranslationProvider):
    """Translation-memory-backed decorator around another TranslationProvider.

    `model_id` identifies the wrapped provider for memory lookups (e.g. "lmstudio:llama-3-8b").
    It must be stable across runs for the memory to pay off, and distinct across models so a
    translation from one model is never served for another.
    """

    def __init__(self, inner: TranslationProvider, memory: TranslationMemory, model_id: str) -> None:
        self.inner = inner
        self.memory = memory
        self.model_id = model_id

    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        results: dict[str, Segment] = {}
        misses: list[Segment] = []
        cached_count = 0
        cached_chars = 0
        total_chars = sum(len(s.source) for s in segments)
        total_segments = len(segments)

        for seg in segments:
            cached = self.memory.get(seg, src_lang, tgt_lang, self.model_id)
            if cached is not None:
                results[seg.block_id] = cached
                cached_count += 1
                cached_chars += len(seg.source)
            else:
                misses.append(seg)

        # Bellek isabetlerini anında bildir / Immediately report cache hits to progress
        if on_progress is not None and cached_count > 0:
            from layoutkeep.providers.batching import BatchProgress

            on_progress(
                BatchProgress(
                    segments_done=cached_count,
                    segments_total=total_segments,
                    chars_done=cached_chars,
                    chars_total=total_chars,
                    elapsed_s=0.0,
                    batch_size=cached_count,
                )
            )

        if misses:
            extra = {}
            if on_progress is not None:
                from layoutkeep.providers.batching import BatchProgress

                def _forward_progress(bp: BatchProgress) -> None:
                    on_progress(
                        BatchProgress(
                            segments_done=cached_count + bp.segments_done,
                            segments_total=total_segments,
                            chars_done=cached_chars + bp.chars_done,
                            chars_total=total_chars,
                            elapsed_s=bp.elapsed_s,
                            batch_size=bp.batch_size,
                        )
                    )

                extra["on_progress"] = _forward_progress

            try:
                fresh = self.inner.translate(misses, src_lang, tgt_lang, glossary, **extra)
            except TypeError:
                fresh = self.inner.translate(misses, src_lang, tgt_lang, glossary)

            for seg in fresh:
                results[seg.block_id] = seg
                self.memory.put(seg, src_lang, tgt_lang, self.model_id)

        return [results[seg.block_id] for seg in segments]

