"""Unit tests for CachedProvider - no network, and a real repetition hit-rate measurement."""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.cached import CachedProvider
from layoutkeep.providers.fake import FakeProvider
from layoutkeep.providers.memory import TranslationMemory


def test_second_run_is_served_entirely_from_memory(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    inner = FakeProvider(translations={"b1": "Bonjour", "b2": "Monde"})
    provider = CachedProvider(inner, memory, model_id="fake-1")

    segments = [Segment(block_id="b1", source="Hello"), Segment(block_id="b2", source="World")]

    first = provider.translate(segments, "en", "fr")
    assert all(not s.from_memory for s in first)
    assert memory.stats() == {"hits": 0, "misses": 2, "entries": 2}

    second = provider.translate(segments, "en", "fr")
    assert all(s.from_memory for s in second)
    assert {s.target for s in second} == {"Bonjour", "Monde"}
    assert memory.stats() == {"hits": 2, "misses": 2, "entries": 2}


def test_only_misses_go_to_inner_provider(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    memory.put(Segment(block_id="b1", source="Hello", target="Bonjour"), "en", "fr", "fake-1")

    inner = FakeProvider(translations={"b2": "Monde"})
    provider = CachedProvider(inner, memory, model_id="fake-1")

    segments = [Segment(block_id="b1", source="Hello"), Segment(block_id="b2", source="World")]
    result = provider.translate(segments, "en", "fr")

    by_id = {s.block_id: s for s in result}
    assert by_id["b1"].from_memory is True
    assert by_id["b2"].from_memory is False
    assert by_id["b2"].target == "Monde"


def test_result_order_matches_input_order(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    memory.put(Segment(block_id="b2", source="World", target="Monde"), "en", "fr", "fake-1")
    inner = FakeProvider(translations={"b1": "Bonjour", "b3": "Chat"})
    provider = CachedProvider(inner, memory, model_id="fake-1")

    segments = [
        Segment(block_id="b1", source="Hello"),
        Segment(block_id="b2", source="World"),
        Segment(block_id="b3", source="Cat"),
    ]
    result = provider.translate(segments, "en", "fr")
    assert [s.block_id for s in result] == ["b1", "b2", "b3"]


def test_book_with_repeated_headers_measures_real_hit_rate(tmp_path):
    """Simulates a 50-page book: each page has a repeated header/footer plus one unique
    body paragraph. Reports the actual translation-memory hit rate across two chapters
    translated back to back (memory persists across the calls, like re-running the tool
    on later pages of the same job)."""
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    inner = FakeProvider()
    provider = CachedProvider(inner, memory, model_id="fake-1")

    num_pages = 50
    total_requests = 0
    for page in range(num_pages):
        segments = [
            Segment(block_id=f"p{page}-header", source="LayoutKeep User Manual"),
            Segment(block_id=f"p{page}-footer", source="Page footer - confidential"),
            Segment(block_id=f"p{page}-body", source=f"Unique paragraph number {page}."),
        ]
        provider.translate(segments, "en", "fr")
        total_requests += len(segments)

    stats = memory.stats()
    hit_rate = stats["hits"] / total_requests
    print(f"\nTM hit rate over {num_pages} simulated pages: {hit_rate:.1%} "
          f"({stats['hits']} hits / {total_requests} requests, {stats['entries']} unique entries)")

    # Header + footer repeat on every page after the first -> (num_pages - 1) * 2 hits.
    assert stats["hits"] == (num_pages - 1) * 2
    assert stats["entries"] == num_pages + 2  # header + footer + one unique body per page
    assert hit_rate > 0.2  # matches the 20-40% savings expected from running headers/footers


def test_budget_capped_request_is_not_served_from_memory_at_full_length(tmp_path):
    """The fit pass's shorten request (`max_len`) must not be answered by a cache hit of the
    original length: rhetorically the same request, but the model would be asked to produce a
    shorter rendering, so a hit at full length is a no-op that makes the shrink ladder give up."""

    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    memory.put(Segment(block_id="b1", source="Hello", target="A very long cached translation"), "en", "fr", "fake-1")
    short = {"b1": "Short."}
    inner = FakeProvider(translations=short)
    provider = CachedProvider(inner, memory, model_id="fake-1")

    result = provider.translate([Segment(block_id="b1", source="Hello", max_len=8)], "en", "fr")
    assert result[0].from_memory is False
    assert result[0].target == "Short."

    # A hit that does fit the cap is still served from memory.
    memory.put(Segment(block_id="b2", source="World", target="Petit"), "en", "fr", "fake-1")
    result = provider.translate(
        [Segment(block_id="b2", source="World", max_len=10), Segment(block_id="b2", source="World")],
        "en", "fr",
    )
    assert result[0].from_memory is True
    assert result[0].target == "Petit"

    # No max_len: unchanged behaviour, full-length hit served (a source the short inner
    # answer has not overwritten - the first miss stored "Short." for b1).
    memory.put(Segment(block_id="b3", source="Tree", target="Arbre tres long ici"), "en", "fr", "fake-1")
    result = provider.translate([Segment(block_id="b3", source="Tree")], "en", "fr")
    assert result[0].from_memory is True
    assert result[0].target == "Arbre tres long ici"
