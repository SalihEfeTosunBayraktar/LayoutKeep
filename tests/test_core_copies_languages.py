"""The number-word tables the README's language claim rests on.

The README says the pipeline works on "Latin scripts (Turkish, English, German, French, Spanish,
…)" and part of what makes that true for a *number* is `spelled_numbers`: a reply that writes
"douze" where the source says "12" is not a lost number. Only Turkish and English were tested -
the German, French and Spanish tables could have rotted unnoticed, and a claim about supported
languages is exactly the kind of thing that must not rest on an untested table.
"""

from __future__ import annotations

from layoutkeep.core.copies import spelled_numbers


def test_german_french_and_spanish_number_words_are_recognised() -> None:
    assert spelled_numbers("zwölf Seiten", "de")["12"] == 1
    assert spelled_numbers("douze chapitres", "fr")["12"] == 1
    assert spelled_numbers("quince páginas", "es")["15"] == 1


def test_the_tables_carry_more_than_one() -> None:
    """A table with only small numbers would silently miss a year or a page count."""
    assert spelled_numbers("mille neuf cent quatre-vingt-quinze", "fr")  # 1995, in French parts
    assert spelled_numbers("mil novecientos noventa y cinco", "es")  # 1995, in Spanish parts
    assert spelled_numbers("zweitausend", "de")["2000"] == 1


def test_ordinals_count_too() -> None:
    assert spelled_numbers("la deuxième partie", "fr")["2"] == 1
    assert spelled_numbers("el segundo capítulo", "es")["2"] == 1
    assert spelled_numbers("der dritte Abschnitt", "de")["3"] == 1


def test_a_language_without_a_table_contributes_nothing() -> None:
    """Unknown is not a loss: the checker stays silent instead of guessing (see the docstring)."""
    assert spelled_numbers("douze", "xx") == {}
    assert spelled_numbers("douze", "") == {}
