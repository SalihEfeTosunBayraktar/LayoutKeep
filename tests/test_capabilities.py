"""Which conversions are open, and that the lock is applied everywhere rather than in one place.

The point of `core/capabilities.py` is that the interface, the command line and the
documentation cannot drift apart on the question. A test that only checked the module would pass
while the CLI happily wrote an EPUB.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core import capabilities


def test_pdf_to_pdf_is_the_only_open_pair():
    assert capabilities.is_open(".pdf", ".pdf")
    assert capabilities.is_open(".PDF", ".pdf"), "the check is case-insensitive"
    for target in (".epub", ".docx", ".html", ".png", ".jpg"):
        assert not capabilities.is_open(".pdf", target)
    for source in (".epub", ".docx", ".png", ".html"):
        assert not capabilities.is_open(source, ".pdf")


def test_same_as_source_resolves_before_it_is_judged():
    """"auto" is open for a PDF and locked for an EPUB, because it means different things."""
    assert capabilities.is_open(".pdf", "auto")
    assert not capabilities.is_open(".epub", "auto")
    assert capabilities.resolve_target(".epub", "auto") == ".epub"


def test_every_locked_target_says_why():
    """A lock with no reason is an interface saying "no" and nothing else."""
    for target in (".epub", ".docx", ".html", ".png", ".jpg"):
        assert capabilities.lock_reason_key(target), f"{target} has no reason"
    assert capabilities.lock_reason_key(".pdf") == ""


def test_the_reasons_exist_in_every_interface_language():
    from layoutkeep.ui.strings import UIStrings

    keys = set(capabilities.LOCK_REASONS.values()) | {
        "LOCKED_SUFFIX", "LOCKED_TITLE", "LOCKED_BODY", "LOCKED_SOURCE_BODY",
    }
    previous = UIStrings.get_language()
    try:
        for lang in ("tr", "en", "de"):
            UIStrings.set_language(lang)
            for key in keys:
                value = UIStrings.get(key)
                assert value and value != key, f"{key} missing in {lang}"
    finally:
        UIStrings.set_language(previous)


def test_the_command_line_refuses_a_locked_pair(tmp_path: Path):
    """The lock has to hold outside the desktop application too, or it is decoration."""
    from layoutkeep.cli import main

    src = Path("docs/samples/sample_report.pdf").resolve()
    with pytest.raises(SystemExit) as caught:
        main([
            "translate", str(src), "--to", "tr",
            "-o", str(tmp_path / "out.epub"), "--provider", "fake",
        ])
    message = str(caught.value)
    assert ".epub" in message
    assert "ENGINE-ARCHITECTURE" in message, "the refusal must point at the evidence"


def test_open_targets_lists_what_can_be_picked():
    assert capabilities.open_targets(".pdf") == ("auto", ".pdf")
    assert capabilities.open_targets(".epub") == ()
