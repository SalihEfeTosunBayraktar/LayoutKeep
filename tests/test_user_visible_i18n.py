"""Pin the rule that every user-visible string exists in tr, en and de.

Covers:
  * tunable labels, help_text, warning and evidence prefixes (these are shown in the settings dialog)
  * review reasons written onto blocks/segments and shown in the completion screen / review list
  * the dedicated fit-review keys (`REVIEW_BOX_CRUSHED`, `REVIEW_FIT_FAILED`)

Internal machine keys (e.g. `box_crushed`) are allowed to stay language-neutral; only the text
that reaches the user is checked.
"""

from __future__ import annotations

import re

from layoutkeep.core import tunables
from layoutkeep.ui.strings import _TRANSLATIONS


def _turkish(s: str) -> bool:
    return bool(re.search(r"[\u00e7\u011f\u0131\u015f\u00f6\u00fc\u00c7\u011e\u0130\u015e\u00d6\u00dc]", s))


def test_every_tunable_user_string_exists_in_all_languages() -> None:
    """Labels, help, warnings and the evidence prefix are displayed; they must have tr/en/de."""
    for spec in tunables.TUNABLES:
        for field in ("label", "help_text", "warning", "evidence"):
            text = getattr(spec, field, "")
            if not text:
                continue
            for lang in ("tr", "en", "de"):
                key = f"TUNABLE_{spec.key}_{field}"
                assert key in _TRANSLATIONS[lang], (
                    f"{lang} missing {key} for tunable {spec.key!r} ({field})"
                )


def test_review_reason_keys_exist_in_all_languages() -> None:
    """Reasons shown to the user (fit failure, glossary miss, etc.) must be translated."""
    user_reason_keys = {
        "REVIEW_FIT_FAILED",
        "REVIEW_BOX_CRUSHED",
        "REVIEW_FORMATTING_LOST",
        "REVIEW_PASSTHROUGH",
        "REVIEW_BATCH_FAILED",
        "REVIEW_GLOSSARY_MISS",
        "REVIEW_BOTTOM_MARGIN",
        "REVIEW_PROVIDER_EMPTY",
        "REVIEW_MIRROR_TEXT",
        "REVIEW_OCR_LOW_CONFIDENCE",
        "REVIEW_PROTECTED_VALUE_LOST",
        "REVIEW_CONTEXT_OVERFLOW",
    }
    for key in user_reason_keys:
        for lang in ("tr", "en", "de"):
            assert key in _TRANSLATIONS[lang], f"{lang} missing review reason {key}"


def test_verify_loss_reasons_exist_in_all_languages() -> None:
    """verify.REVIEW_REASONS are written onto blocks; each kind must be translatable."""
    from layoutkeep import verify

    for kind in verify.REVIEW_REASONS:
        key = f"VERIFY_REVIEW_{kind}"
        for lang in ("tr", "en", "de"):
            assert key in _TRANSLATIONS[lang], f"{lang} missing verify review reason {key}"


def test_format_review_reason_resolves_a_stored_key_in_every_language() -> None:
    """The display-time resolver turns a stored key into the active language, never leaking it."""
    from layoutkeep.ui.strings import UIStrings, format_review_reason

    previous = UIStrings.get_language()
    try:
        for lang in ("tr", "en", "de"):
            UIStrings.set_language(lang)
            text = format_review_reason("REVIEW_FIT_FAILED")
            assert text and text != "REVIEW_FIT_FAILED"
    finally:
        UIStrings.set_language(previous)


def test_format_review_reason_maps_pipe_arguments_to_placeholders() -> None:
    """`REVIEW_PROTECTED_VALUE_LOST|3` fills the translated template's `{lost}`, positionally."""
    from layoutkeep.ui.strings import UIStrings, format_review_reason

    previous = UIStrings.get_language()
    try:
        UIStrings.set_language("en")
        text = format_review_reason("REVIEW_PROTECTED_VALUE_LOST|3")
        assert "3" in text
        assert "{lost}" not in text
    finally:
        UIStrings.set_language(previous)


def test_format_review_reason_leaves_legacy_and_empty_values_unchanged() -> None:
    """Projects written before reasons became keys hold plain sentences; they keep displaying."""
    from layoutkeep.ui.strings import format_review_reason

    assert format_review_reason("") == ""
    assert format_review_reason("korunan değer çeviride yok") == "korunan değer çeviride yok"
