"""The application sends its batches in parallel, and reports them in document order.

The bug this holds shut: the application sent one request at a time while the command line had
been translating seven chunks at once for months - with LM Studio set to seven slots, which exists
for exactly that. Reported from a running job: "7 slots configured, one request in flight".

Two things have to stay true together: the requests really do overlap, and the translation comes
back in document order regardless of which request finished first.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import pytest

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.ui.translation_loop import _run_translation_loop

KEY = "translation.workers"
CHUNK = "batch.chunk_size"


class _Signal:
    def __init__(self) -> None:
        self.emissions: list[tuple] = []

    def emit(self, *args: object) -> None:
        self.emissions.append(args)


class _Status:
    def __init__(self) -> None:
        self.phases: list[str] = []

    def emit(self, phase: str) -> None:
        self.phases.append(phase)


@dataclass
class _ProviderConfig:
    timeout: float | None = None
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "stub"


@dataclass
class _Config:
    provider: _ProviderConfig = field(default_factory=_ProviderConfig)


class _Worker:
    """The parts of the real worker the loop touches, with no Qt in the way."""

    def __init__(self) -> None:
        self.status = _Status()
        self.progress = _Signal()
        self.progress_detailed = _Signal()
        self.active_segment = _Signal()
        self.batch_timeout = _Signal()
        self.segment_translated = _Signal()
        self.review_flags = _Signal()
        self.memory_stats = _Signal()
        self.failed = _Signal()
        self._cancelled = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._config = _Config()


class _OverlapProvider:
    """Records how many translations were in flight at once, and returns a marker per segment."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.in_flight = 0
        self.peak = 0
        self.lock = threading.Lock()

    def translate(self, segments, **kwargs):
        with self.lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            time.sleep(self.delay)
            for segment in segments:
                segment.target = f"T:{segment.source}"
            return segments
        finally:
            with self.lock:
                self.in_flight -= 1


@pytest.fixture(autouse=True)
def _restore_settings() -> None:
    before = (tunables.get(KEY), tunables.get(CHUNK))
    yield
    tunables.set_value(KEY, before[0])
    tunables.set_value(CHUNK, before[1])


def _segments(count: int) -> list[Segment]:
    return [Segment(block_id=f"b{i}", source=f"sentence {i}") for i in range(count)]


def test_batches_really_overlap(monkeypatch) -> None:
    """With four workers, four requests are in flight - not one."""
    provider = _OverlapProvider()
    monkeypatch.setattr(
        "layoutkeep.ui.worker._build_provider", lambda config: (provider, None, None)
    )
    tunables.set_value(KEY, 4)
    tunables.set_value(CHUNK, 4)  # 16 segments -> 4 batches, so the wave has something to overlap
    worker = _Worker()
    segments = _segments(16)
    chunk = int(tunables.get("batch.chunk_size"))
    batches = -(-len(segments) // chunk)

    result = _run_translation_loop(
        worker, provider, None, segments, len(segments), 100, source_lang="en", target_lang="tr"
    )

    assert result is not None and len(result) == 16
    assert provider.peak > 1, f"{batches} batches went out one at a time"
    assert provider.peak <= 4, "more requests in flight than workers configured"


def test_one_worker_stays_sequential(monkeypatch) -> None:
    provider = _OverlapProvider()
    monkeypatch.setattr(
        "layoutkeep.ui.worker._build_provider", lambda config: (provider, None, None)
    )
    tunables.set_value(KEY, 1)
    tunables.set_value(CHUNK, 4)
    worker = _Worker()
    segments = _segments(8)

    result = _run_translation_loop(
        worker, provider, None, segments, len(segments), 100, source_lang="en", target_lang="tr"
    )

    assert result is not None
    assert provider.peak == 1


def test_the_translation_comes_back_in_document_order(monkeypatch) -> None:
    """Whichever request finishes first, the output follows the document."""
    provider = _OverlapProvider(delay=0.02)
    monkeypatch.setattr(
        "layoutkeep.ui.worker._build_provider", lambda config: (provider, None, None)
    )
    tunables.set_value(KEY, 4)
    tunables.set_value(CHUNK, 4)
    worker = _Worker()
    segments = _segments(16)

    result = _run_translation_loop(
        worker, provider, None, segments, len(segments), 100, source_lang="en", target_lang="tr"
    )

    assert result is not None
    assert [seg.source for seg in result] == [seg.source for seg in segments]
    assert [seg.target for seg in result] == [f"T:{seg.source}" for seg in segments]


def test_a_short_document_still_fills_the_configured_slots(monkeypatch) -> None:
    """Driving the 0.9.10 exe: 32 segments with eight workers and batches of twenty went out as two
    requests, one after the other in practice. A short document is split into smaller batches so
    every configured slot has one - never below the floor, so a batch still carries context."""
    provider = _OverlapProvider()
    monkeypatch.setattr(
        "layoutkeep.ui.worker._build_provider", lambda config: (provider, None, None)
    )
    tunables.set_value(KEY, 8)
    tunables.set_value(CHUNK, 20)
    worker = _Worker()
    segments = _segments(32)

    result = _run_translation_loop(
        worker, provider, None, segments, len(segments), 100, source_lang="en", target_lang="tr"
    )

    assert result is not None and [seg.source for seg in result] == [seg.source for seg in segments]
    assert provider.peak == 8, f"only {provider.peak} of 8 slots were used"


def test_a_tiny_document_keeps_batches_of_the_floor_size(monkeypatch) -> None:
    provider = _OverlapProvider()
    monkeypatch.setattr(
        "layoutkeep.ui.worker._build_provider", lambda config: (provider, None, None)
    )
    tunables.set_value(KEY, 8)
    tunables.set_value(CHUNK, 20)
    worker = _Worker()

    result = _run_translation_loop(
        worker, provider, None, _segments(8), 8, 100, source_lang="en", target_lang="tr"
    )

    assert result is not None
    assert provider.peak == 2, "8 segments at a floor of 4 per batch are two requests"
