"""A book translated in chunks is translated with one term list, not one per chunk.

WHY THIS EXISTS: `translate_book.py` runs one `layoutkeep translate` per chunk, and with
`translation.auto_glossary` on every chunk built its own glossary from its own page. Page one could
settle "tokeniser" as "belirteçleyici" and page three as "tokenleştirici" - the inconsistency the
glossary exists to remove. The bench measured EN->TR consistency at 86.4% with terms like that.

The fix: the whole input is asked for its terms once (`translate --terms-only`), and every chunk is
handed that list with its own automatic list switched off (`--no-auto-glossary`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "audit"))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

import build_epub_fixture
import translate_book

from layoutkeep import cli
from layoutkeep.core import tunables


def _chunk_args(**extra) -> Namespace:
    base = {
        "to": "tr", "base_url": "http://x/v1", "model": "m", "timeout": 0, "layout_detector": False,
        "preserve_references": False, "fit_mode": None, "memory": "", "resume": False, "glossary": None,
    }
    base.update(extra)
    return Namespace(**base, **{"from": "en"})


def _captured_command(tmp_path: Path, monkeypatch, args: Namespace) -> list[str]:
    seen: list[list[str]] = []

    def fake_run(command, **_kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(translate_book.subprocess, "run", fake_run)
    translate_book.translate_chunk(tmp_path / "c.pdf", tmp_path / "t_0000.pdf", args)
    return seen[0]


def test_a_chunk_is_given_the_document_glossary_and_builds_none_of_its_own(tmp_path, monkeypatch):
    command = _captured_command(tmp_path, monkeypatch, _chunk_args(glossary=str(tmp_path / "g.json")))

    assert command[command.index("--glossary") + 1] == str(tmp_path / "g.json")
    assert "--no-auto-glossary" in command


def test_without_a_document_glossary_a_chunk_runs_as_before(tmp_path, monkeypatch):
    command = _captured_command(tmp_path, monkeypatch, _chunk_args())

    assert "--glossary" not in command
    assert "--no-auto-glossary" not in command


def test_the_automatic_glossary_is_not_built_when_switched_off(monkeypatch):
    def explode(_provider):
        raise AssertionError("the model must not be asked for terms")

    monkeypatch.setattr("layoutkeep.providers.base.chat_callable", explode)
    args = cli.build_parser().parse_args(["translate", "x.pdf", "--to", "tr", "--no-auto-glossary"])
    tunables.set_value("translation.auto_glossary", True)
    try:
        assert cli._automatic_glossary(None, object(), args) == {}
    finally:
        tunables.set_value("translation.auto_glossary", False)


def test_terms_only_writes_the_glossary_and_translates_nothing(tmp_path, monkeypatch, capsys):
    source = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(source)
    out = tmp_path / "doc.epub"
    monkeypatch.setattr(cli, "_automatic_glossary", lambda doc, provider, args: {"bold": "kalın"})

    tunables.set_value("translation.auto_glossary", True)
    try:
        code = cli.main(["translate", str(source), "--from", "en", "--to", "tr",
                         "--provider", "fake", "--output", str(out), "--terms-only"])
    finally:
        tunables.set_value("translation.auto_glossary", False)

    assert code == cli.EXIT_OK, capsys.readouterr().out
    assert json.loads((tmp_path / "doc.glossary.json").read_text(encoding="utf-8")) == {"bold": "kalın"}
    assert not out.exists()


def test_the_book_tool_reads_the_stored_settings(tmp_path, monkeypatch):
    """Like the CLI (D-020): without loading them, the book never saw `auto_glossary` switched on."""
    settings = tmp_path / "tunables.json"
    settings.write_text(json.dumps({"translation.auto_glossary": True}), encoding="utf-8")
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(settings))
    monkeypatch.setattr(sys, "argv", ["translate_book", "in.pdf", "--out", "o.pdf", "--model", "m"])

    class StopError(Exception):
        pass

    def stop(_args):
        raise StopError

    monkeypatch.setattr(translate_book, "_prepare_work_dir", stop)
    with pytest.raises(StopError):
        translate_book.main()
    try:
        assert tunables.get("translation.auto_glossary") is True
    finally:
        tunables.reset_all()
