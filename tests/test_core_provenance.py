"""What a run says about itself: version, provider, endpoint, settings, reader path.

WHY THIS EXISTS: a translated document does not say what produced it. Two runs of the same source
with a different build, a different model or a different reader are indistinguishable afterwards,
so a comparison cannot be trusted and a result cannot be reproduced - the question "which version,
with what, and with which methods was this translated?" has to be answerable from the file.

The two rules these tests hold to: the record is a fact about the run rather than a guess, and a
credential never reaches it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from layoutkeep import __version__
from layoutkeep.core import provenance, tunables
from layoutkeep.core.docir import Document, Page, from_dict, load_project, save_project

SHA_RE = re.compile(r"[0-9a-f]{40}")


# -- what a record contains ------------------------------------------------------------------------


def test_a_run_records_the_version_and_what_translated_it() -> None:
    info = provenance.collect(
        provider_kind="openai",
        model="google/gemma-4-e4b",
        base_url="http://127.0.0.1:1234/v1",
        source_lang="en",
        target_lang="tr",
        reader="digital",
        fit_mode="strict",
        glossary={"bold": "kalın"},
        memory=True,
    )

    assert info["app_version"] == __version__
    assert info["provider"] == "openai"
    assert info["model"] == "google/gemma-4-e4b"
    assert info["endpoint"] == "http://127.0.0.1:1234/v1"
    assert (info["source_lang"], info["target_lang"]) == ("en", "tr")
    assert info["reader"] == "digital"
    assert info["fit_mode"] == "strict"
    assert info["translation_memory"] is True
    assert info["glossary"]["terms"] == 1
    assert info["glossary"]["fingerprint"]
    # A source checkout names its commit; a packaged build has none. Both are recorded, neither
    # is invented.
    assert info["commit"] is None or SHA_RE.fullmatch(info["commit"])
    assert datetime.fromisoformat(info["started"]).tzinfo == UTC


def test_a_run_without_a_glossary_does_not_claim_one() -> None:
    info = provenance.collect(provider_kind="fake")
    assert info["glossary"] is None
    assert info["translation_memory"] is False


def test_a_provider_that_has_no_model_or_url_of_its_own_records_neither() -> None:
    """The test provider and DeepL translate without an endpoint of this machine's choosing.

    Recording the LM Studio default that happened to sit in the form would be a fiction, and a
    record that can be wrong is worse than one that says nothing.
    """
    info = provenance.collect(provider_kind="fake", model="google/gemma-4-e4b",
                             base_url="http://127.0.0.1:1234/v1")
    assert info["model"] == "fake"
    assert info["endpoint"] == ""


# -- a credential never reaches the record ---------------------------------------------------------


def test_a_key_pasted_into_the_endpoint_is_not_recorded() -> None:
    info = provenance.collect(
        provider_kind="openai",
        base_url="https://user:s3cret@api.example.com/v1?api_key=abc123&stream=true",
    )

    assert info["endpoint"] == "https://api.example.com/v1?stream=true"
    assert "s3cret" not in json.dumps(info)
    assert "abc123" not in json.dumps(info)


# -- the settings that differ from the defaults ----------------------------------------------------


def test_only_the_settings_that_differ_are_recorded() -> None:
    assert tunables.get("translation.workers") == 2
    tunables.set_value("translation.workers", 5)
    try:
        info = provenance.collect(provider_kind="fake")
    finally:
        tunables.reset("translation.workers")

    assert info["settings"] == {"translation.workers": 5}


# -- how the pages were read -----------------------------------------------------------------------


def test_the_reader_path_says_how_the_pages_were_actually_read() -> None:
    digital = Document(pages=[Page(number=1, width=100, height=100)])
    scanned = Document(pages=[Page(number=1, width=100, height=100, scanned=True)])

    assert provenance.reader_path(digital) == "digital"
    assert provenance.reader_path(digital, layout_model=True) == "digital+layout"
    assert provenance.reader_path(scanned) == "ocr"
    assert (
        provenance.reader_path(scanned, layout_model=True, layout_classifier=True)
        == "ocr+layout+vlm"
    )


def test_the_fitting_mode_in_force_is_read_from_the_one_setting() -> None:
    assert provenance.fit_mode_name() == "strict"
    tunables.set_value("fitting.reflow", True)
    try:
        assert provenance.fit_mode_name() == "reflow"
    finally:
        tunables.reset("fitting.reflow")


# -- the commit ------------------------------------------------------------------------------------


def test_a_source_checkout_reports_its_commit() -> None:
    """Read straight from `.git`, not by running git: the record is built at the end of a run.

    A linked worktree - which is where this test runs - keeps its HEAD in the worktree's git
    directory and its refs in the common one, so a naive read finds nothing at all.
    """
    assert SHA_RE.fullmatch(provenance.git_commit() or "")


def test_a_packaged_build_reports_no_commit_instead_of_failing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(provenance, "__file__", str(tmp_path / "lk" / "core" / "provenance.py"))
    assert provenance.git_commit() is None


def test_a_plain_checkout_is_read_too(monkeypatch, tmp_path) -> None:
    """The ordinary case: `.git` is a directory and the branch has a loose ref."""
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("b" * 40 + "\n", encoding="utf-8")
    monkeypatch.setattr(provenance, "__file__", str(tmp_path / "src" / "core" / "provenance.py"))

    assert provenance.git_commit() == "b" * 40


# -- the project file ------------------------------------------------------------------------------


def test_a_project_keeps_the_record_and_an_older_one_still_loads(tmp_path: Path) -> None:
    doc = Document(pages=[Page(number=1, width=100, height=100)], source_lang="en",
                   target_lang="tr")
    info = provenance.record(
        doc, provider_kind="fake", source_lang="en", target_lang="tr", fit_mode="strict"
    )
    assert provenance.of(doc) == info

    path = tmp_path / "run.lkproj"
    save_project(doc, path)
    assert load_project(path).provenance == info

    # A project written before the record existed has no such key, and must still load: the
    # field is optional, not a schema change.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("provenance")
    assert from_dict(payload).provenance is None


def test_the_summary_line_is_what_a_reader_of_the_file_sees() -> None:
    info = {"app_version": "0.9.10", "model": "google/gemma-4-e4b", "commit": "a" * 40}
    assert provenance.summary(info) == f"LayoutKeep 0.9.10 · google/gemma-4-e4b · {'a' * 10}"

    packaged = provenance.summary({"app_version": "0.9.10", "model": "fake", "commit": None})
    assert packaged == "LayoutKeep 0.9.10 · fake · packaged build"
