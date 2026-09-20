"""The help screen describes what the program does - including what was added most recently.

Twice now a feature landed and the help stayed as it was: the glossary/memory wiring, and this
release's bilingual output, presets and term suggestions. A help screen that is one release behind
is worse than a short one, because a reader trusts it. This file holds the line: every feature the
setup screen offers is named in the help, in both languages the help has.
"""

from __future__ import annotations

import pytest

from layoutkeep.ui import help_text

#: A phrase that must appear somewhere in the help, per language. Which section names it is the
#: author's choice; that it is named at all is the requirement.
FEATURES = [
    {"tr": "Sayfa aralığı", "en": "Page range"},
    {"tr": "Çift dilli PDF", "en": "Bilingual PDF"},
    {"tr": "hazır ayar", "en": "preset"},
    {"tr": "Belgeden öner", "en": "Suggest from document"},
    {"tr": "Pencereye dön", "en": "Back to window"},
    {"tr": "Çeviri belleği", "en": "translation memory"},
]


def _body(language: str, section: str) -> str:
    return help_text.text(language, section)["body"]


def _whole_help(language: str) -> str:
    return " ".join(_body(language, section) for section in help_text.SECTIONS)


@pytest.mark.parametrize("phrases", FEATURES)
@pytest.mark.parametrize("language", ["tr", "en"])
def test_the_help_names_the_feature(language: str, phrases: dict[str, str]) -> None:
    # Case-insensitive: the help writes "çeviri belleği" mid-sentence, and the point is that the
    # feature is named, not how it is capitalised.
    assert phrases[language].casefold() in _whole_help(language).casefold(), (
        f"the {language} help does not mention {phrases[language]!r} anywhere - "
        "the help is behind the interface"
    )


def test_every_section_has_a_title_and_a_body_in_both_languages() -> None:
    for language in ("tr", "en"):
        for section in help_text.SECTIONS:
            copy = help_text.text(language, section)
            assert copy.get("title"), f"{language}/{section} has no title"
            assert len(copy.get("body", "")) > 80, f"{language}/{section} body is suspiciously short"


def test_a_language_without_its_own_help_falls_back_to_english() -> None:
    """German has interface strings but no help sections; the fallback must be the English text,
    not an empty panel."""
    copy = help_text.text("de", "settings")

    assert "preset" in copy["body"] or "Developer" in copy["body"]
