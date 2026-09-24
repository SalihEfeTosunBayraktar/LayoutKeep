"""Soft hyphens for German: where they go, and where they never go."""

from __future__ import annotations

from layoutkeep.core.hyphenate import SOFT_HYPHEN, hyphenate_word, soft_hyphens


def _parts(word: str) -> list[str]:
    return hyphenate_word(word).split(SOFT_HYPHEN)


def test_a_long_word_gets_break_points_that_rebuild_it():
    for word in ("Steuererklärungen", "Aufzeichnungen", "Tokenisierungsalgorithmen", "Regierungsbehörden"):
        parts = _parts(word)
        assert "".join(parts) == word
        assert len(parts) > 1, word
        assert all(len(part) >= 3 for part in (parts[0], parts[-1])), parts


def test_vowel_pairs_and_consonant_groups_are_never_split():
    text = hyphenate_word("Aufzeichnungen") + hyphenate_word("Verschiebungen") + hyphenate_word("Druckerzeugnisse")
    for pair in ("au", "ei", "sch", "ck", "ie"):
        assert f"{pair[0]}{SOFT_HYPHEN}{pair[1:]}" not in text


def test_short_words_codes_and_acronyms_stay_whole():
    for word in ("Steuern", "Größe", "IRS.gov/Form1040", "NASA-Programm", "iPhoneKamera"):
        assert SOFT_HYPHEN not in soft_hyphens(word, "de"), word


def test_only_a_hyphenated_language_is_touched():
    assert soft_hyphens("Steuererklärungen", "en") == "Steuererklärungen"
    assert SOFT_HYPHEN in soft_hyphens("Die Steuererklärungen sind fällig", "de")
    assert SOFT_HYPHEN in soft_hyphens("Steuererklärungen", "de-DE")


def test_turkish_breaks_at_its_syllables():
    for word, expected in (
        ("kitaplıklardaki", ["ki", "tap", "lık", "lar", "da", "ki"]),
        ("yönetmeliklerinde", ["yö", "net", "me", "lik", "le", "rin", "de"]),
        ("Cumhurbaşkanlığı", ["Cum", "hur", "baş", "kan", "lı", "ğı"]),
    ):
        parts = hyphenate_word(word, "tr").split(SOFT_HYPHEN)
        # The first and last parts keep at least three letters, so the edge syllables merge.
        assert "".join(parts) == word
        assert all(p in "".join(expected) for p in parts)
        assert len(parts) >= 3, parts


def test_turkish_text_is_hyphenated_and_english_is_not():
    assert SOFT_HYPHEN in soft_hyphens("Değerlendirmelerimizi paylaştık", "tr")
    assert SOFT_HYPHEN not in soft_hyphens("Understandably, internationalization", "en")
