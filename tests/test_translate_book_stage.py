"""A failing chunk must say which stage it died in.

WHY THIS EXISTS: the first chunk of the scanned Eleventh Development Plan failed on every run and the
campaign reported `exit=1` plus a few interesting lines. The chunk's own log ends on library noise, so
placing the failure - the writer, below Python, with no traceback - meant reading the pipeline's stage
order and matching it against the log by hand. Naming the stage costs nothing and turns that hunt into
one word in the progress line.

The fixture below is the tail of that real log, kept verbatim.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "audit"))
sys.path.insert(0, str(Path(__file__).parent))

from translate_book import _stage_reached

#: The last lines of `_artifacts/heldout/live/tr_plan_11/out/t_0000.log` as the failing run left them.
REAL_FAILING_TAIL = """protect   63 literal values held back from the model, 29 NOT returned - those segments flagged
retry     20 segments recovered on a second attempt
translated 82/82 in 0.0s  cached=82
memory    122/122 hits (100%), 32456 entries stored
length    target/source = 0.97x measured  (-0.03 vs the 1.00x assumed)
fitting   82 blocks: as_is=16 shrunk=37 retranslated=19 expanded=1 overflow=9
          9 still overflow - flagged for review
review    34 segment(s) flagged for review
'created' timestamp out of range; ignoring top bytes
'created' timestamp seems very low; regarding as unix timestamp
cannot reshape array of size 32770400 into shape (3425, 2392, 3)"""


def test_the_real_failure_is_placed_after_the_review_stage() -> None:
    """The log ends on library noise; the last stage it reached is what names the culprit."""
    assert _stage_reached(REAL_FAILING_TAIL) == "review"


def test_the_last_stage_wins_when_several_are_present() -> None:
    log = "reading   chunk.pdf\nsegments  82\nfitting   82 blocks: as_is=16\nwrote     out/t_0000.pdf\n"

    assert _stage_reached(log) == "wrote"


def test_a_log_that_never_started_reports_unknown() -> None:
    assert _stage_reached("") == "unknown"
    assert _stage_reached("Traceback (most recent call last):\n  File \"x.py\", line 1\n") == "unknown"


def test_a_line_that_merely_contains_a_stage_name_is_not_a_stage() -> None:
    """Only the first word counts, or a sentence about fitting would be read as the fitting stage."""
    log = "review    34 segment(s) flagged for review\nthe fitting pass asked for a shorter rendering\n"

    assert _stage_reached(log) == "review"


def test_a_failed_chunk_reports_the_stage_in_its_progress_line(tmp_path: Path, monkeypatch) -> None:
    """The end of it: the progress line a campaign prints names the stage. Red before the change."""
    import argparse

    import translate_book

    class _Result:
        returncode = 1
        stdout = REAL_FAILING_TAIL
        stderr = ""

    monkeypatch.setattr(translate_book.subprocess, "run", lambda *a, **k: _Result())
    args = argparse.Namespace(
        resume=False,
        to="en",
        base_url="http://127.0.0.1:1234/v1",
        model="google/gemma-4-e4b",
        timeout=None,
        layout_detector=True,
        preserve_references=False,
        fit_mode=None,
        memory=None,
    )
    args.__dict__["from"] = "tr"

    _out, code, tail = translate_book.translate_chunk(tmp_path / "chunk_0000.pdf", tmp_path / "t_0000.pdf", args)

    assert code == 1
    assert "died after 'review'" in tail
