"""A chunk that failed gets exactly one more try before its document is given up on.

WHY THIS EXISTS: the TR -> EN campaign ran for hours, and its last document came back with
`1 chunk(s) produced no output; not merging a document with holes`. The chunk had failed on a defect
in the writer, not on the model, and nothing retried it - the document sat one chunk short until
someone looked. A single sequential retry turns that into a finished document, while a chunk that
fails twice stays a real failure and is reported as one.

The tests drive `_retry_failed` with a stubbed `translate_chunk`, so no model server is involved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "audit"))
sys.path.insert(0, str(Path(__file__).parent))

import translate_book


def test_a_failed_chunk_is_retried_once_into_the_same_output(tmp_path: Path, monkeypatch) -> None:
    attempts: list[str] = []

    def fake_chunk(path: Path, out: Path, args) -> tuple[Path, int, str]:
        attempts.append(out.name)
        return out, 0, "attempt"  # the retry succeeds

    monkeypatch.setattr(translate_book, "translate_chunk", fake_chunk)

    still_failing = translate_book._retry_failed([(0, tmp_path / "src" / "chunk_0000.pdf")], tmp_path, None)

    assert attempts == ["t_0000.pdf"], "the retry must write the same chunk output, exactly once"
    assert still_failing == 0, "a retry that succeeds clears the failure"


def test_a_chunk_that_fails_twice_is_reported_as_failing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(translate_book, "translate_chunk", lambda path, out, args: (out, 1, "attempt"))

    assert translate_book._retry_failed([(3, tmp_path / "c.pdf")], tmp_path, None) == 1


def test_nothing_is_run_when_no_chunk_failed(tmp_path: Path, monkeypatch) -> None:
    def explode(*_args, **_kwargs):
        raise AssertionError("no chunk failed, so no chunk should be run")

    monkeypatch.setattr(translate_book, "translate_chunk", explode)

    assert translate_book._retry_failed([], tmp_path, None) == 0


def test_every_failed_chunk_is_retried_once_in_index_order(tmp_path: Path, monkeypatch) -> None:
    seen: list[str] = []

    def fake_chunk(path: Path, out: Path, args) -> tuple[Path, int, str]:
        seen.append(out.name)
        return out, 0, "attempt"

    monkeypatch.setattr(translate_book, "translate_chunk", fake_chunk)
    failed = [(7, tmp_path / "c7.pdf"), (2, tmp_path / "c2.pdf")]

    translate_book._retry_failed(failed, tmp_path, None)

    assert seen == ["t_0002.pdf", "t_0007.pdf"], "chunks are retried in index order, once each"
