"""Tests for protected literals.

The cases here are not invented. Every one is a real string measured out of a document this
project was pointed at: a CLAAS baler manual read through OCR, and a US tax form read from its
text layer. The patterns exist because those values would otherwise have been handed to a
translation model.
"""

from __future__ import annotations

import pytest

from layoutkeep.core.protect import (
    DEFAULT_PATTERNS,
    describe,
    is_data_only,
    protect,
    restore,
)

# Measured out of the CLAAS QUADRANT 5300 tying-adjustment manual.
MANUAL_CASES = [
    ("between 0.05 and 0.2 mm.", "pair"),
    ("Tighten the 4 bolts (4) to torque of: 63 Nm,", "measurement"),
    ("Tighten the bolts (3) to 150 Nm.", "measurement"),
    ("Tighten the bolt (4) to 24.5 Nm.", "measurement"),
    ("28+1 mm.", "tolerance"),
    # OCR flattens the superscript tolerance, and every engine does it differently.
    ("Step 3: 3-1 Adjust the knotter nose spring (5): 33* mm", "ocr_tolerance"),
    ("It must be 50 =20 mm, and if necessary, adjust the brake settings.", "ocr_tolerance"),
    # The part number identifies the exact manual revision.
    ("00 0288 280 0 - EN-US - 09.2016", "partnumber"),
]

# Measured out of IRS Form W-4.
FORM_CASES = [
    ("If your total income will be $200,000 or less ($400,000 if married).", "currency"),
    ("OMB No. 1545-0074", "identifier"),
]


@pytest.mark.parametrize(("text", "expected_kind"), MANUAL_CASES + FORM_CASES)
def test_real_document_values_are_protected(text: str, expected_kind: str) -> None:
    protection = protect(text)
    assert protection.count >= 1, f"nothing protected in {text!r}"
    assert expected_kind in protection.kinds.values(), (
        f"expected a {expected_kind} in {text!r}, got {sorted(set(protection.kinds.values()))}"
    )


@pytest.mark.parametrize("text", [t for t, _ in MANUAL_CASES + FORM_CASES])
def test_round_trip_is_exact(text: str) -> None:
    """The whole point: what goes in comes back byte-identical."""
    protection = protect(text)
    restored, missing = restore(protection.text, protection)
    assert restored == text
    assert missing == 0


@pytest.mark.parametrize("text", [t for t, _ in MANUAL_CASES + FORM_CASES])
def test_protected_values_are_hidden_from_the_model(text: str) -> None:
    """A model cannot rewrite what it never sees, which is the entire defence."""
    protection = protect(text)
    for literal in protection.literals.values():
        assert literal not in protection.text


def test_restoration_reads_from_the_source_not_the_reply() -> None:
    """A model that mangles the words around a token must not be able to corrupt its value.

    This is why literals are restored from the mapping rather than parsed back out of the reply.
    """
    protection = protect("Tighten the bolts to 150 Nm.")
    translated = protection.text.replace("Tighten the bolts to", "Cıvataları şu değere sıkın:")
    restored, missing = restore(translated, protection)
    assert "150 Nm" in restored
    assert missing == 0


def test_a_dropped_token_is_reported_rather_than_silently_lost() -> None:
    """A missing token means the value is absent from the translation. The caller must know."""
    protection = protect("Tighten the bolts to 150 Nm.")
    restored, missing = restore("Cıvataları sıkın.", protection)
    assert missing == 1
    assert "150 Nm" not in restored


def test_callouts_survive_reordering() -> None:
    """Turkish word order differs from English, so a callout moves within the sentence.

    It must still carry the same number - a reader sent to part (3) instead of part (4) is worse
    off than one given no translation at all.
    """
    source = "Loosen the 4 bolts (4)."
    protection = protect(source)
    assert protection.count >= 1
    reordered = "".join(reversed(protection.text.split()))  # violent reordering
    restored, missing = restore(reordered, protection)
    assert missing == 0
    assert "(4)" in restored


@pytest.mark.parametrize("text", ["1", "19,999", "  42  ", "3.14", "$1,000"])
def test_data_only_segments_are_recognised(text: str) -> None:
    assert is_data_only(text)


@pytest.mark.parametrize(
    "text",
    [
        "Step 2",
        "Loosen the 4 bolts",
        "Between 10 and 20 people attended.",  # no unit: ordinary prose, not a measurement
        "",
    ],
)
def test_ordinary_text_is_not_treated_as_data(text: str) -> None:
    assert not is_data_only(text)


def test_prose_without_values_is_left_alone() -> None:
    """Over-protection is its own failure: tokens fragment a sentence and degrade the translation."""
    text = "Pull the knotter backward to capture the clearance."
    protection = protect(text)
    assert protection.count == 0
    assert protection.text == text


def test_describe_summarises_what_was_protected() -> None:
    protection = protect("Tighten the bolts (3) to 150 Nm and the bolt (4) to 24.5 Nm.")
    summary = describe(protection)
    assert "callout" in summary
    assert "measurement" in summary


def test_every_pattern_compiles_and_is_named() -> None:
    import re

    for name, pattern in DEFAULT_PATTERNS:
        assert name.isidentifier(), f"{name!r} must be usable as a regex group name"
        re.compile(pattern)
