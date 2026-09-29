"""A run must never read another document's chunk files.

WHY THIS EXISTS: `--work` used to default to a shared `_artifacts/book` that accumulates the chunks of
every run which never passed the flag. A fresh 24-page paper was cut from that directory's leftovers,
translated, and came back carrying another document's text - half an hour of model time and a silently
wrong answer, caught only because a human read the output. The default is now derived from `--out`, and
a work directory whose marker names a different input is refused instead of quietly reused.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "audit"))
sys.path.insert(0, str(Path(__file__).parent))

from translate_book import _WORK_INPUT_MARKER, _prepare_work_dir


def _args(tmp_path: Path, *, work: Path | None = None, force: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        input=tmp_path / "sources" / "paper.pdf",
        out=tmp_path / "runs" / "paper.en.pdf",
        work=work,
        force=force,
    )


def test_without_work_the_directory_is_derived_from_the_output(tmp_path: Path) -> None:
    """Two runs for different outputs can never share a directory."""
    work = _prepare_work_dir(_args(tmp_path))

    assert work == tmp_path / "runs" / "paper.en_work"
    assert (work / "src").is_dir() and (work / "out").is_dir()


def test_the_directory_records_which_input_its_chunks_came_from(tmp_path: Path) -> None:
    work = _prepare_work_dir(_args(tmp_path))

    assert (work / _WORK_INPUT_MARKER).read_text(encoding="utf-8").strip().endswith("paper.pdf")


def test_a_directory_cut_from_another_input_is_refused(tmp_path: Path) -> None:
    work = _prepare_work_dir(_args(tmp_path))
    (work / _WORK_INPUT_MARKER).write_text(str(tmp_path / "sources" / "other.pdf"), encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        _prepare_work_dir(_args(tmp_path))

    message = str(caught.value)
    assert "other.pdf" in message and "paper.pdf" in message, "the refusal must name both inputs"


def test_the_same_input_may_be_resumed(tmp_path: Path) -> None:
    first = _prepare_work_dir(_args(tmp_path))
    (first / "out" / "t_0000.pdf").write_bytes(b"%PDF-1.4\n")  # a chunk from the first run

    second = _prepare_work_dir(_args(tmp_path))  # --resume depends on this passing

    assert second == first
    assert (second / "out" / "t_0000.pdf").exists(), "a resumed run keeps the chunks already written"


def test_force_reuses_a_directory_that_belongs_to_another_input(tmp_path: Path) -> None:
    work = _prepare_work_dir(_args(tmp_path))
    (work / _WORK_INPUT_MARKER).write_text(str(tmp_path / "sources" / "other.pdf"), encoding="utf-8")

    assert _prepare_work_dir(_args(tmp_path, force=True)) == work


def test_an_explicit_work_directory_is_used_as_given(tmp_path: Path) -> None:
    chosen = tmp_path / "elsewhere" / "book"

    assert _prepare_work_dir(_args(tmp_path, work=chosen)) == chosen
