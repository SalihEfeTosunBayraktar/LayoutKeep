"""Unit tests for TranslationMemory - no network, temp SQLite files."""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.memory import TranslationMemory


def test_miss_then_put_then_hit(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    seg = Segment(block_id="b1", source="Hello")

    assert memory.get(seg, "en", "fr", "model-a") is None

    translated = Segment(block_id="b1", source="Hello", target="Bonjour")
    memory.put(translated, "en", "fr", "model-a")

    hit = memory.get(seg, "en", "fr", "model-a")
    assert hit is not None
    assert hit.target == "Bonjour"
    assert hit.from_memory is True
    assert hit.block_id == "b1"


def test_key_includes_model_identity(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    seg = Segment(block_id="b1", source="Hello", target="Bonjour")
    memory.put(seg, "en", "fr", "model-a")

    # Same source/langs, different model -> must not be served.
    miss = memory.get(Segment(block_id="b1", source="Hello"), "en", "fr", "model-b")
    assert miss is None


def test_key_includes_langs(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    seg = Segment(block_id="b1", source="Hello", target="Bonjour")
    memory.put(seg, "en", "fr", "model-a")

    miss = memory.get(Segment(block_id="b1", source="Hello"), "en", "de", "model-a")
    assert miss is None


def test_stats_track_hits_misses_entries(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    seg = Segment(block_id="b1", source="Hello", target="Bonjour")

    memory.get(Segment(block_id="b1", source="Hello"), "en", "fr", "model-a")  # miss
    memory.put(seg, "en", "fr", "model-a")
    memory.get(Segment(block_id="b1", source="Hello"), "en", "fr", "model-a")  # hit
    memory.get(Segment(block_id="b1", source="Hello"), "en", "fr", "model-a")  # hit

    stats = memory.stats()
    assert stats == {"hits": 2, "misses": 1, "entries": 1}


def test_db_created_on_demand(tmp_path):
    db_path = tmp_path / "nested" / "tm.sqlite3"
    db_path.parent.mkdir()
    memory = TranslationMemory(db_path)
    assert db_path.exists()
    memory.close()


def test_put_without_target_is_noop(tmp_path):
    memory = TranslationMemory(tmp_path / "tm.sqlite3")
    memory.put(Segment(block_id="b1", source="Hello", target=""), "en", "fr", "model-a")
    assert memory.stats()["entries"] == 0
