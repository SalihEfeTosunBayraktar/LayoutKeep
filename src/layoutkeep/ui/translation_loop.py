"""The translation loop of the application worker: batched, and parallel.

WHY THIS EXISTS: the application sent one request at a time. The command line has translated seven
chunks at once for a long time and the LM Studio slot count exists for exactly that, so the
application was the slow way to run the same engine - reported, correctly, as "7 slots configured,
one request in flight". Batches now go out in waves of `translation.workers`; a wave waits for its
members, so pause and cancel still take effect at a boundary, and results are merged in document
order so the output never depends on which request finished first.

Kept apart from `worker.py` for the same reason the fitting passes were split: the class is Qt
plumbing and this is the part with the numbers in it.
"""

from __future__ import annotations

import concurrent.futures
import time

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.ui.strings import UIStrings

#: The smallest batch a short document is cut into, so each request keeps some context.
_MIN_BATCH = 4


def _segment_preview(source_text: str) -> str:
    """Build the short single-line preview shown next to the active segment."""
    clean = source_text.strip().replace("\n", " ")
    return clean[:77] + "…" if len(clean) > 80 else clean


def _translate_one_batch(
    provider,
    batch: list[Segment],
    source_lang: str,
    target_lang: str,
    glossary: dict[str, str] | None,
) -> list[Segment]:
    """One request-batch in a worker thread: no Qt, no shared state, safe to run in parallel."""
    return provider.translate(batch, src_lang=source_lang, tgt_lang=target_lang, glossary=glossary)


def _provider_pool(config, primary, count: int) -> list:
    """One provider chain per parallel worker.

    The chain carries per-run state - the dedupe cache, the translation-memory connection - so
    sharing one instance across threads would be a race, not a saving. Extra chains are built from
    the same config, so they translate the same way.
    """
    if count <= 1:
        return [primary]
    from layoutkeep.ui.worker import _build_provider  # local: worker imports this module

    pool = [primary]
    for _ in range(count - 1):
        other, _memory, _terms = _build_provider(config)
        pool.append(other)
    return pool


def _wait_while_paused(worker) -> bool:
    """Block at a boundary while the run is paused. False means it was cancelled instead."""
    if not worker._pause_event.is_set():
        worker.status.emit(UIStrings.STATUS_PAUSED)
    while not worker._pause_event.is_set():
        if worker._cancelled:
            return False
        time.sleep(0.1)
    return True


def _run_translation_loop(
    worker,
    provider,
    memory,
    segments: list[Segment],
    total: int,
    total_chars: int,
    *,
    source_lang: str,
    target_lang: str,
    glossary: dict[str, str] | None = None,
) -> list[Segment] | None:
    """Translate `segments`, `translation.workers` batches at a time; None if cancelled or failed."""
    from layoutkeep.ui.worker import (
        _compute_batch_timeout,
        _connection_error_message,
        _timeout_error_message,
    )

    workers = max(1, int(tunables.get("translation.workers") or 1))
    # A short document is cut into smaller batches so every configured slot gets one: 32 segments
    # in batches of twenty were two requests for eight slots. Never below the floor - a batch still
    # has to carry some context for the model.
    configured = int(tunables.get("batch.chunk_size"))
    chunk_size = min(configured, max(_MIN_BATCH, -(-total // workers)))
    batches = [segments[start : start + chunk_size] for start in range(0, total, chunk_size)]
    providers = _provider_pool(worker._config, provider, workers)

    worker.status.emit("translating")
    translated: list[Segment] = []
    chars_per_second: float | None = None
    done_chars = 0

    for wave_start in range(0, len(batches), workers):
        if worker._cancelled:
            worker.status.emit("cancelled")
            return None
        if not _wait_while_paused(worker):
            worker.status.emit("cancelled")
            return None

        wave = batches[wave_start : wave_start + workers]
        wave_chars = sum(len(seg.source) for batch in wave for seg in batch)
        worker.active_segment.emit(wave_start + 1, _segment_preview(wave[0][0].source))
        timeout = _compute_batch_timeout(
            provider,
            worker._config.provider.timeout,
            wave_chars,
            is_first=wave_start == 0,
            chars_per_second=chars_per_second,
        )
        for pooled in providers:
            _set_timeout(pooled, timeout)
        worker.batch_timeout.emit(timeout)

        hits_before = memory.stats()["hits"] if memory is not None else 0
        started = time.monotonic()

        results: list[list[Segment] | None] = [None] * len(wave)
        failure: tuple[str, object] | None = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(wave))) as pool:
            futures = {
                pool.submit(
                    _translate_one_batch,
                    providers[index % len(providers)],
                    batch,
                    source_lang,
                    target_lang,
                    glossary,
                ): index
                for index, batch in enumerate(wave)
            }
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except TimeoutError:
                    failure = ("timeout", None)
                except OSError as exc:
                    failure = ("connection", exc)

        if failure is not None:
            kind, exc = failure
            if kind == "timeout":
                worker.failed.emit(_timeout_error_message(worker._config.provider.base_url, timeout))
            else:
                worker.failed.emit(_connection_error_message(worker._config.provider.base_url, exc))
            return None

        produced_any = False
        for batch_result in results:
            if batch_result is None:
                continue
            produced_any = True
            translated.extend(batch_result)
            for produced in batch_result:
                if produced.target:
                    worker.segment_translated.emit(
                        _segment_preview(produced.source), _segment_preview(produced.target)
                    )

        elapsed = time.monotonic() - started
        hit_this = memory is not None and memory.stats()["hits"] > hits_before
        # A memory-hit wave returns in ~0s; its "speed" is not a measurement, so leave the estimate
        # alone (the ETA calculator treats 0.0 as "no measurement").
        measured = produced_any and wave_chars > 0 and elapsed > 0 and not hit_this
        if measured:
            chars_per_second = wave_chars / elapsed
        done_chars += wave_chars

        worker.review_flags.emit(sum(1 for seg in translated if seg.needs_review), len(translated))
        rate = chars_per_second if measured else 0.0
        worker.progress.emit(len(translated), total)
        worker.progress_detailed.emit(len(translated), total, done_chars, total_chars, rate, "")
        if memory is not None:
            stats = memory.stats()
            worker.memory_stats.emit(stats["hits"], stats["hits"] + stats["misses"])

    return translated


def _set_timeout(provider, timeout: float) -> None:
    """Push a timeout through whatever wrappers the provider chain has."""
    from layoutkeep.ui.worker import _set_provider_timeout

    _set_provider_timeout(provider, timeout)
