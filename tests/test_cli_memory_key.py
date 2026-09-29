"""The command line's memory key: a changed glossary must not answer from an earlier run's rows.

`--memory` serves a segment from a stored translation when the key matches, and the key is
(source text, source language, target language, model). A glossary changes what the model is asked
for, so a translation made under a different term list is not an answer to this run's question. The
desktop chain folds a fingerprint of the glossary into its model id
(`ui/worker._build_provider`); the command line's `_build_provider` did not, so
`--memory --glossary` served translations produced before the terms changed.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from layoutkeep import cli

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture

#: Two term lists that disagree about the same source term: one document, two questions. The
#: fixture's chapter one holds the word "bold", so the term policy is really in play.
FIRST_GLOSSARY = {"bold": "kalın"}
SECOND_GLOSSARY = {"bold": "koyu"}


def _source(tmp_path: Path) -> Path:
    """The sample EPUB: fixed, offline text for the runs below to translate."""
    source = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(source)
    return source


def _glossary_file(tmp_path: Path, name: str, terms: dict[str, str]) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _run(capsys, source: Path, glossary: str, memory: Path, out: Path) -> str:
    """One real run of the command line, returning what it printed."""
    code = cli.main(
        [
            "translate", str(source), "--from", "en", "--to", "tr", "--provider", "fake",
            "--output", str(out), "--memory", str(memory), "--glossary", glossary,
        ]
    )
    printed = capsys.readouterr().out
    assert code == cli.EXIT_OK, printed
    return printed


def _cached(printed: str) -> int:
    """How many segments the memory answered, read from the CLI's own summary line."""
    line = next(line for line in printed.splitlines() if "cached=" in line)
    return int(line.split("cached=")[1])


def _models(memory: Path) -> set[str]:
    """The model identities rows were stored under - one per distinct question."""
    with sqlite3.connect(memory) as conn:
        return {row[0] for row in conn.execute("SELECT DISTINCT model FROM translations")}


def _model_id(provider) -> str:
    """The identity the memory is keyed by, wherever the cache sits in the wrapper chain."""
    while provider is not None:
        if hasattr(provider, "model_id"):
            return provider.model_id
        provider = getattr(provider, "inner", None)
    raise AssertionError("no translation memory in the provider chain")


def _args(*argv: str):
    """The real parser's view of a command line, so the test reads the options the CLI reads."""
    return cli.build_parser().parse_args(["translate", *argv])


def _window_key(glossary: str, memory: Path) -> str:
    """The key the application's own chain computes for that glossary - the one to match."""
    from layoutkeep.ui.job import JobConfig, ProviderConfig
    from layoutkeep.ui.worker import _build_provider as build_window_provider

    config = JobConfig(
        input_path="in.epub",
        output_path="out.epub",
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake"),
        glossary_path=glossary,
        memory_path=str(memory),
    )
    provider, built_memory, _terms = build_window_provider(config)
    assert built_memory is not None, "the window built no memory for this job"
    return _model_id(provider)


# -- what a run actually reuses --------------------------------------------------------------------


def test_a_changed_glossary_is_not_answered_from_the_earlier_run(tmp_path, capsys):
    source = _source(tmp_path)
    memory = tmp_path / "memory.sqlite"
    first = _glossary_file(tmp_path, "first.json", FIRST_GLOSSARY)
    second = _glossary_file(tmp_path, "second.json", SECOND_GLOSSARY)

    fresh = _run(capsys, source, first, memory, tmp_path / "first.out.epub")
    assert _cached(fresh) == 0, f"the first run had nothing to reuse:\n{fresh}"

    changed = _run(capsys, source, second, memory, tmp_path / "second.out.epub")
    assert _cached(changed) == 0, (
        "the second term list was answered from the first one's translations:\n" + changed
    )
    # Two term lists, two keys: the rows written under the first must not be reachable from the
    # second, and the second's own rows have to be there for a later run to reuse.
    assert len(_models(memory)) == 2, _models(memory)


def test_the_same_glossary_still_reuses_its_own_rows(tmp_path, capsys):
    """The control: the fingerprint must separate glossaries, not disable the memory."""
    source = _source(tmp_path)
    memory = tmp_path / "memory.sqlite"
    glossary = _glossary_file(tmp_path, "same.json", FIRST_GLOSSARY)

    _run(capsys, source, glossary, memory, tmp_path / "one.out.epub")
    again = _run(capsys, source, glossary, memory, tmp_path / "two.out.epub")

    assert _cached(again) > 0, f"an unchanged glossary no longer reuses its own rows:\n{again}"


# -- the key itself --------------------------------------------------------------------------------


def test_the_cli_keys_its_memory_the_way_the_window_does(tmp_path):
    """Same document, same glossary, same memory file: the two front-ends must agree on the key.

    One key for both, because they are the same job: a window run of a document the command line
    has already translated should reuse those rows, and a run under a changed glossary must not.
    """
    source = _source(tmp_path)
    glossary = _glossary_file(tmp_path, "one.json", FIRST_GLOSSARY)
    args = _args(
        str(source), "--from", "en", "--to", "tr", "--provider", "fake",
        "--output", str(tmp_path / "out.epub"), "--memory", str(tmp_path / "memory.sqlite"),
        "--glossary", glossary,
    )

    provider, memory = cli._build_provider(args)

    assert memory is not None, "the memory option did not reach the chain"
    assert _model_id(provider) != "fake", "the glossary is not in the key at all"
    assert _model_id(provider) == _window_key(glossary, tmp_path / "window.sqlite")


def test_the_cli_key_covers_the_automatic_terms_too(tmp_path, capsys, monkeypatch):
    """`--glossary` plus the document's own terms: the merged list is what gets translated.

    The window builds its chain a second time once the merged list is on disk, so its key carries
    those terms; the command line kept the key of the file alone.
    """
    from layoutkeep.core import tunables
    from layoutkeep.core.doc_glossary import merge_glossaries

    source = _source(tmp_path)
    user_file = _glossary_file(tmp_path, "user.json", FIRST_GLOSSARY)
    automatic = {"italic": "eğik"}
    # The model's answer stands in for the one chat call the run would make.
    monkeypatch.setattr(cli, "_automatic_glossary", lambda doc, provider, args: automatic)

    tunables.set_value("translation.auto_glossary", True)
    try:
        ran = _run(capsys, source, user_file, tmp_path / "auto.sqlite", tmp_path / "auto.out.epub")
    finally:
        tunables.set_value("translation.auto_glossary", False)
    assert "automatic terms" in ran, ran

    # The list the run wrote is the one it translated with: the model's term and the file's.
    merged_file = tmp_path / "auto.out.glossary.json"
    merged = json.loads(merged_file.read_text(encoding="utf-8"))
    assert merged == merge_glossaries(automatic, FIRST_GLOSSARY), merged

    assert _models(tmp_path / "auto.sqlite") == {
        _window_key(str(merged_file), tmp_path / "window.sqlite")
    }, _models(tmp_path / "auto.sqlite")
    # and not the key of the user's file on its own, which is what it used to store under
    assert _models(tmp_path / "auto.sqlite") != {
        _window_key(user_file, tmp_path / "window-plain.sqlite")
    }
