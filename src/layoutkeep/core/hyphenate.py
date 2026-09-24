"""Soft hyphens in long words, so a narrow box can break a word instead of shrinking the text.

WHY THIS EXISTS: German runs long words together ("Tokenisierungsalgorithmen", "Steuererklärungen").
A box a third as wide as such a word can only fit it by shrinking the whole block - MuPDF measured
one of them at 52% of its size - and a block below the readability floor is flagged (D1). On the
EN->DE bench 46 blocks of one IRS form were flagged, and in over a third the longest word alone was
wider than most of its line. MuPDF breaks a line at a soft hyphen (U+00AD) and draws the hyphen
only where it breaks, so the same word fits at full size.

No dictionary ships with the application, so the break points come from the plain rules of German
syllables: a single consonant between vowels starts the next syllable, of a run of consonants the
last one does - or the run a syllable can start with (kl, sp, st, tr ...); vowel pairs (ei, au, ie
...) and sch, ch, ck, ph, qu are never split; at least
three letters stay on either side. A compound's joint is sometimes missed ("Tokenisierung-salgo..."
where a dictionary would give "...rungs-al..."), which reads a little oddly but stays readable -
the alternative was text too small to read.

Only the text drawn on the page carries the hyphens (`writers/pdf_writer`, `fitting/pdf_pass`): the
document's own text, the glossary check and the translation memory never see them.
"""

from __future__ import annotations

import re
from itertools import pairwise

SOFT_HYPHEN = "­"

#: Languages whose long words are broken; the rules below are German's.
HYPHENATED_LANGUAGES = frozenset({"de"})

#: Shorter words are left whole: the gain is small and a broken short word reads worst.
_MIN_WORD = 10
#: Letters kept on either side of a break.
_MIN_PART = 3

_VOWELS = "aeiouäöüy"
_VOWEL_PAIRS = ("ai", "ei", "au", "eu", "äu", "ie", "aa", "ee", "oo")
_CONSONANT_UNITS = ("sch", "ch", "ck", "ph", "qu")
#: Consonant runs a German syllable can start with: a break keeps the longest of them together
#: ("Er-klä-rung", "hoch-spe-zia-li-siert", "Ein-kom-men-steu-er").
_ONSETS = frozenset((
    "bl", "br", "chr", "dr", "fl", "fr", "gl", "gr", "kl", "kn", "kr", "pf", "pfl", "pfr",
    "phr", "pl", "pr", "qu", "schl", "schm", "schn", "schr", "schw", "sk", "sp", "spl", "spr", "st",
    "str", "tr", "zw",
))
_WORD = re.compile("[A-Za-zÄÖÜäöüß]+")


def _break_points(word: str) -> list[int]:
    """Indexes inside `word` where a soft hyphen may go."""
    lower = word.lower()
    # Tokenise into (kind, start, end): vowel groups and consonant units.
    units: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lower):
        if lower[i] in _VOWELS:
            end = i + 2 if lower[i : i + 2] in _VOWEL_PAIRS else i + 1
            units.append(("v", i, end))
            i = end
            continue
        for unit in _CONSONANT_UNITS:
            if lower.startswith(unit, i):
                units.append(("c", i, i + len(unit)))
                i += len(unit)
                break
        else:
            units.append(("c", i, i + 1))
            i += 1
    points: list[int] = []
    vowel_at = [n for n, unit in enumerate(units) if unit[0] == "v"]
    for left, right in pairwise(vowel_at):
        cluster = units[left + 1 : right]
        if not cluster:
            continue  # two vowels side by side: no break between them
        point = cluster[-1][1]  # before the last consonant unit, or before a longer onset
        for unit in cluster[:-1]:
            if lower[unit[1] : cluster[-1][2]] in _ONSETS:
                point = unit[1]
                break
        if _MIN_PART <= point <= len(word) - _MIN_PART:
            points.append(point)
    return points


def hyphenate_word(word: str) -> str:
    """`word` with soft hyphens at its break points, or unchanged when it is short or not a word."""
    if len(word) < _MIN_WORD or any(ch.isupper() for ch in word[1:]):
        return word
    points = _break_points(word)
    if not points:
        return word
    parts, last = [], 0
    for point in points:
        parts.append(word[last:point])
        last = point
    parts.append(word[last:])
    return SOFT_HYPHEN.join(parts)


def soft_hyphens(text: str, lang: str | None) -> str:
    """`text` with soft hyphens in its long words, for a language that is hyphenated; else as is."""
    if not text or (lang or "").split("-")[0].lower() not in HYPHENATED_LANGUAGES:
        return text
    return _WORD.sub(lambda match: hyphenate_word(match.group(0)), text)
