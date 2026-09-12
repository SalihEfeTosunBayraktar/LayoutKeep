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

#: The five pairs measured at 100% across every metric in format_matrix.json.
MEASURED_PAIRS = [
    (".pdf", ".pdf"),
    (".pdf", ".docx"),
    (".epub", ".epub"),
    (".docx", ".docx"),
    (".png", ".docx"),
]


def test_measured_pairs_are_open():
    """Every conversion the matrix measures at 100% is open."""
    for source, target in MEASURED_PAIRS:
        assert capabilities.is_open(source, target), f"{source}->{target} should be open"


def test_measured_pairs_are_case_insensitive():
    """The check is case-insensitive, like the rest of the system."""
    assert capabilities.is_open(".PDF", ".DOCX")
    assert capabilities.is_open(".EPUB", ".epub")


def test_same_as_source_resolves_before_it_is_judged():
    """"auto" resolves to the source format. If that pair is open the
    conversion is allowed; if it is locked the conversion is refused."""
    assert capabilities.is_open(".pdf", "auto")  # diagonal: open
    assert capabilities.is_open(".epub", "auto")  # diagonal: open
    assert capabilities.is_open(".docx", "auto")  # diagonal: open
    assert not capabilities.is_open(".png", "auto")  # png→png is locked
    assert not capabilities.is_open(".html", "auto")  # cross-format: locked
    assert capabilities.resolve_target(".epub", "auto") == ".epub"


def test_every_locked_target_says_why():
    """A lock with no reason is an interface saying "no" and nothing else."""
    for target in (".epub", ".html", ".png", ".jpg"):
        assert capabilities.lock_reason_key(target), f"{target} has no reason"
    assert capabilities.lock_reason_key(".pdf") == ""
    assert capabilities.lock_reason_key(".docx") == ""


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
    assert capabilities.open_targets(".pdf") == ("auto", ".pdf", ".docx")
    assert capabilities.open_targets(".epub") == ("auto", ".epub")
    assert capabilities.open_targets(".docx") == ("auto", ".docx")
    assert capabilities.open_targets(".png") == (".docx",)
    assert capabilities.open_targets(".html") == ()
