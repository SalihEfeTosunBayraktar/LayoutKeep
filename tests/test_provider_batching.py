"""Unit tests for providers/batching.py. No network."""

from __future__ import annotations

import pytest

from layoutkeep.core.docir import Segment
from layoutkeep.providers.batching import (
    AdaptiveBatchSize,
    BatchProgress,
    BatchTooLargeError,
    batch_timeout,
    chunk_segments,
    run_batches,
)


def _seg(block_id: str, chars: int) -> Segment:
    return Segment(block_id=block_id, source="x" * chars)


def test_chunk_segments_fills_batches_up_to_budget():
    # max_segments=None: budget purely by characters, so the count cap (default 1, see
    # DEFAULT_MAX_SEGMENTS) does not also apply here.
    segments = [_seg("a", 100), _seg("b", 100), _seg("c", 100)]
    batches = chunk_segments(segments, max_chars=250, max_segments=None)
    assert [[s.block_id for s in b] for b in batches] == [["a", "b"], ["c"]]


def test_chunk_segments_never_splits_a_single_oversized_segment():
    segments = [_seg("a", 500), _seg("b", 10)]
    batches = chunk_segments(segments, max_chars=100, max_segments=None)
    assert [[s.block_id for s in b] for b in batches] == [["a"], ["b"]]


def test_chunk_segments_counts_context_towards_the_budget():
    seg = Segment(block_id="a", source="x" * 50, context_before="y" * 50, context_after="y" * 50)
    batches = chunk_segments([seg, _seg("b", 50)], max_chars=150, max_segments=None)
    # a alone already uses 150 chars (50 source + 50 + 50 context), so b must not join it.
    assert [[s.block_id for s in b] for b in batches] == [["a"], ["b"]]


def test_chunk_segments_empty_input():
    assert chunk_segments([], max_chars=100) == []


def test_chunk_segments_default_caps_one_segment_per_batch():
    """DEFAULT_MAX_SEGMENTS=1: even segments that would easily fit together on character budget
    alone are not combined unless a caller explicitly raises max_segments (see batching.py's
    module docstring for the measured reliability evidence behind this default)."""
    segments = [_seg("a", 10), _seg("b", 10), _seg("c", 10)]
    batches = chunk_segments(segments, max_chars=1000)
    assert [[s.block_id for s in b] for b in batches] == [["a"], ["b"], ["c"]]


def test_batch_timeout_first_batch_gets_a_larger_base_allowance():
    warm = batch_timeout(1000, is_first=False, chars_per_second=100)
    cold = batch_timeout(1000, is_first=True, chars_per_second=100)
    assert cold > warm


def test_batch_timeout_uses_measured_rate_over_the_default_guess():
    slow_guess = batch_timeout(1000, is_first=False, chars_per_second=None)
    fast_measured = batch_timeout(1000, is_first=False, chars_per_second=1000.0)
    assert fast_measured < slow_guess


def test_batch_timeout_is_clamped_both_ends():
    assert batch_timeout(1, is_first=False, chars_per_second=1000000) >= 30.0
    assert batch_timeout(10**9, is_first=False, chars_per_second=0.001) <= 900.0


def test_run_batches_splits_calls_and_preserves_order_by_id():
    segments = [_seg("a", 100), _seg("b", 100), _seg("c", 100)]
    calls: list[list[str]] = []

    def translate_batch(batch):
        calls.append([s.block_id for s in batch])
        return [
            Segment(block_id=s.block_id, source=s.source, target=f"T-{s.block_id}")
            for s in batch
        ]

    results = run_batches(segments, max_chars=250, translate_batch=translate_batch, max_segments=None)
    assert calls == [["a", "b"], ["c"]]
    by_id = {s.block_id: s.target for s in results}
    assert by_id == {"a": "T-a", "b": "T-b", "c": "T-c"}


def test_run_batches_one_failed_batch_does_not_lose_earlier_successes():
    """A batch that fails after an earlier one already succeeded must not abort the run - it
    comes back needs_review, the batches around it are kept."""
    segments = [_seg("a", 100), _seg("b", 100), _seg("c", 100)]

    def translate_batch(batch):
        if any(s.block_id == "b" for s in batch):
            raise TimeoutError("server did not answer")
        return [
            Segment(block_id=s.block_id, source=s.source, target=f"T-{s.block_id}")
            for s in batch
        ]

    # Each segment its own batch, so the failure of "b" is isolated.
    results = run_batches(segments, max_chars=1, translate_batch=translate_batch)
    by_id = {s.block_id: s for s in results}
    assert by_id["a"].target == "T-a"
    assert by_id["a"].needs_review is False
    assert by_id["c"].target == "T-c"
    assert by_id["b"].target == ""
    assert by_id["b"].needs_review is True


def test_run_batches_first_batch_failure_propagates_instead_of_being_swallowed():
    """Nothing has been salvaged yet when the very first batch fails, so there is no partial
    progress to protect - the exception must reach the caller (cli.py / the GUI worker already
    turn it into a clear message) instead of quietly finishing with everything needs_review."""
    segments = [_seg("a", 100), _seg("b", 100)]

    def translate_batch(batch):
        raise TimeoutError("server did not answer")

    with pytest.raises(TimeoutError):
        run_batches(segments, max_chars=1, translate_batch=translate_batch)


def test_run_batches_empty_segments_returns_empty_without_calling_translate_batch():
    calls = []
    results = run_batches([], max_chars=100, translate_batch=lambda b: calls.append(b))
    assert results == []
    assert calls == []


def test_run_batches_reports_progress_after_each_batch():
    segments = [_seg("a", 100), _seg("b", 100), _seg("c", 100)]
    progress: list[BatchProgress] = []

    def translate_batch(batch):
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    run_batches(segments, max_chars=250, translate_batch=translate_batch, on_progress=progress.append, max_segments=None)

    assert len(progress) == 2  # two batches: [a, b] then [c]
    assert progress[0].segments_done == 2
    assert progress[0].segments_total == 3
    assert progress[1].segments_done == 3
    assert progress[1].chars_done == 300
    assert progress[1].chars_total == 300
    assert progress[0].elapsed_s >= 0
    assert progress[1].elapsed_s >= progress[0].elapsed_s


# -- AdaptiveBatchSize (unit) ------------------------------------------------------------


def test_adaptive_batch_size_grows_by_one_on_each_success():
    size = AdaptiveBatchSize()
    assert size.current == 1
    for expected in (2, 3, 4, 5):
        size.record_success()
        assert size.current == expected


def test_adaptive_batch_size_failure_becomes_a_permanent_ceiling():
    size = AdaptiveBatchSize()
    for _ in range(5):
        size.record_success()
    assert size.current == 6
    size.record_failure(6)
    assert size.current == 5
    # further successes must never grow back up to (or past) the failed size.
    for _ in range(10):
        size.record_success()
    assert size.current == 5


def test_adaptive_batch_size_never_shrinks_below_one():
    size = AdaptiveBatchSize()
    size.record_failure(1)
    assert size.current == 1


def test_adaptive_batch_size_respects_max_size_cap():
    size = AdaptiveBatchSize(max_size=3)
    for _ in range(10):
        size.record_success()
    assert size.current == 3


# -- run_batches with adaptive sizing (default max_segments) ----------------------------


def test_run_batches_adaptive_grows_batch_size_on_repeated_success():
    """With nothing else limiting it, the batch size should climb by one after every batch
    that comes back fully translated - 1, 2, 3, 4, 5 for 15 segments (1+2+3+4+5=15)."""
    segments = [_seg(f"s{i}", 1) for i in range(15)]
    sizes: list[int] = []

    def translate_batch(batch):
        sizes.append(len(batch))
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    results = run_batches(segments, max_chars=10_000, translate_batch=translate_batch)

    assert sizes == [1, 2, 3, 4, 5]
    assert len(results) == 15
    assert all(not s.needs_review for s in results)


def test_run_batches_adaptive_shrinks_and_retries_on_protocol_failure():
    """A batch rejected as too large (BatchTooLargeError) must not be given up on - it is
    retried at a smaller size instead of coming back needs_review, and that size becomes a
    ceiling the run never tries again."""
    segments = [_seg(f"s{i}", 1) for i in range(10)]
    attempted_sizes: list[int] = []

    def translate_batch(batch):
        attempted_sizes.append(len(batch))
        if len(batch) >= 4:
            raise BatchTooLargeError("reply came back short")
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    results = run_batches(segments, max_chars=10_000, translate_batch=translate_batch)

    # size 4 was tried and rejected exactly once - it must never be retried after that.
    assert attempted_sizes.count(4) == 1
    assert all(n < 4 for n in attempted_sizes if n != 4)
    # every segment still comes back translated - the rejected batch was recovered, not lost.
    assert len(results) == 10
    assert all(not s.needs_review for s in results)
    assert all(s.target == "t" for s in results)


def test_run_batches_adaptive_does_not_shrink_on_transport_failure():
    """A timeout/connection error is not evidence the batch was too big, so it must not become
    a ceiling - the same (or a larger) size must be tried again afterwards."""
    segments = [_seg(f"s{i}", 1) for i in range(20)]
    attempted_sizes: list[int] = []
    raised_once = {"done": False}

    def translate_batch(batch):
        attempted_sizes.append(len(batch))
        if len(batch) == 3 and not raised_once["done"]:
            raised_once["done"] = True
            raise TimeoutError("server did not answer")
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    results = run_batches(segments, max_chars=10_000, translate_batch=translate_batch)

    # growth continued past the size that hit the transport failure - proof it was not capped.
    assert max(attempted_sizes) > 3
    assert attempted_sizes.count(3) >= 2  # size 3 was retried later, not permanently blocked
    by_id = {s.block_id: s for s in results}
    failed_ids = [f"s{i}" for i in range(3, 6)]  # the batch consumed when the timeout hit
    for block_id in failed_ids:
        assert by_id[block_id].needs_review is True
    assert sum(1 for s in results if s.needs_review) == 3


def test_run_batches_pinned_max_segments_never_adapts():
    """Passing an explicit int for `max_segments` opts out of adaptive sizing entirely - every
    batch stays that exact size, which is what a reproducible benchmark run needs."""
    segments = [_seg(f"s{i}", 1) for i in range(9)]
    sizes: list[int] = []

    def translate_batch(batch):
        sizes.append(len(batch))
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    run_batches(segments, max_chars=10_000, translate_batch=translate_batch, max_segments=3)

    assert sizes == [3, 3, 3]


def test_run_batches_reports_current_batch_size_via_progress():
    segments = [_seg(f"s{i}", 1) for i in range(3)]
    progress: list[BatchProgress] = []

    def translate_batch(batch):
        return [Segment(block_id=s.block_id, source=s.source, target="t") for s in batch]

    run_batches(
        segments, max_chars=10_000, translate_batch=translate_batch, on_progress=progress.append
    )

    # adaptive, starting at 1: first batch is size 1, growing afterwards.
    assert [p.batch_size for p in progress] == [1, 2]
