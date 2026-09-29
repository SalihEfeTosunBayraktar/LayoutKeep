"""The translation memory and the glossary, as the application configures them.

Both existed on the command line only: `--memory` and `--glossary` had no way in from the app, so
the desktop version silently translated without either. These tests pin the wiring - the settings
that feed them, and the promise that a glossary change is not served from a stale memory entry.
"""

from __future__ import annotations

import json

import pytest

from layoutkeep.core import tunables
from layoutkeep.providers.memory import TranslationMemory
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import (
    GlossaryUnreadableError,
    _build_provider,
    _glossary_fingerprint,
    load_glossary_terms,
)


def _job(tmp_path, **kwargs) -> JobConfig:
    defaults = {
        "input_path": str(tmp_path / "in.pdf"),
        "output_path": str(tmp_path / "out.pdf"),
        "source_lang": "English",
        "target_lang": "Turkish",
        "provider": ProviderConfig(kind="fake", base_url="", model="fake", api_key=""),
    }
    defaults.update(kwargs)
    return JobConfig(**defaults)


def _write_glossary(tmp_path, terms: dict[str, str]) -> str:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_both_switches_are_tunables_with_sane_defaults():
    assert tunables.get("translation.memory") is True
    assert tunables.get("translation.glossary_path") == ""


def test_a_configured_glossary_file_reaches_the_provider(tmp_path):
    path = _write_glossary(tmp_path, {"Annual Report": "Yıllık Rapor"})

    provider, _memory, terms = _build_provider(_job(tmp_path, glossary_path=path))

    assert terms == {"Annual Report": "Yıllık Rapor"}
    assert provider is not None


def test_a_broken_glossary_file_does_not_stop_the_job(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(GlossaryUnreadableError):
        load_glossary_terms(str(broken))

    # and the job builder swallows that, so the run goes ahead without a glossary
    provider, _memory, terms = _build_provider(_job(tmp_path, glossary_path=str(broken)))
    assert terms is None
    assert provider is not None


def test_the_memory_key_changes_when_the_glossary_changes(tmp_path):
    """The memory is keyed by (source, languages, model); a glossary changes the request, so it
    has to change the key - otherwise a translation made under the old term policy comes back."""
    first = _glossary_fingerprint({"Annual Report": "Yıllık Rapor"})
    second = _glossary_fingerprint({"Annual Report": "Senelik Rapor"})

    assert first != second
    assert len(first) == 12


def test_a_glossary_run_does_not_reuse_an_unglossed_translation(tmp_path):
    from layoutkeep.providers.fake import FakeProvider

    memory = TranslationMemory(tmp_path / "memory.sqlite")
    path = _write_glossary(tmp_path, {"Report": "Rapor"})
    terms = load_glossary_terms(path)
    assert terms is not None

    plain_key = "fake|none"
    glossary_key = f"fake|gloss:{_glossary_fingerprint(terms)}"

    provider, _memory, _terms = _build_provider(_job(tmp_path, memory_path=str(tmp_path / "m.sqlite")))

    # Two stacks over the same memory file, with different keys: the second must not be served
    # the first one's entry, which is what the fingerprint is there to prevent.
    from layoutkeep.providers.cached import CachedProvider

    cached_plain = CachedProvider(FakeProvider(), memory, plain_key)
    cached_gloss = CachedProvider(FakeProvider(), memory, glossary_key)
    segment = _segment("Report")

    cached_plain.translate([segment], src_lang="English", tgt_lang="Turkish")
    cached_gloss.translate([segment], src_lang="English", tgt_lang="Turkish")

    assert memory.stats()["entries"] == 2  # iki ayrı anahtar, iki ayrı kayıt
    assert provider is not None


def _segment(text: str):
    from layoutkeep.core.docir import Segment

    return Segment(block_id="s1", source=text)
