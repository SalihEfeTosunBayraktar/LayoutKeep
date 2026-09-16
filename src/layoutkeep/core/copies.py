"""Is a reply a translation, or the source handed back?

One definition, used wherever a reply is accepted: the retry pass (`providers/retry.py`), the
passthrough report (`providers/passthrough.py`), the fitting pass (`fitting/fit.py`) and the
lossless audit. It lived in two places with two meanings, and the gap between them is how a
paragraph on book page 61 stayed English through every safeguard: fitting compared a reply with
the source *including* its inline style markers, the English reply had none, so "not equal" -
and the English was accepted.

Pure text, no DocIR, so both the provider and the fitting layer can use it.
"""

from __future__ import annotations

import re
from collections import Counter

_MARKER = re.compile(r"</?\d+>")
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)

#: Share of a reply's words that also appear in its source, at or above which the reply is the
#: source rather than a translation of it. A translation keeps names, acronyms and technical
#: terms and changes the rest; a majority of shared words means the rest did not change either.
#: Language-independent: it compares the two texts, not a word list.
COPY_SHARE = 0.5

#: Fewer distinct words than this and the share is too coarse to mean anything.
COPY_MIN_WORDS = 4


def normalised(text: str) -> str:
    """Markers removed, whitespace collapsed, case folded."""
    return " ".join(_MARKER.sub("", text).split()).casefold()


def content_words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(_MARKER.sub("", text))}


#: Text a translation keeps as it is, whatever the language: anything in quotation marks (a
#: program's output, a title) and addresses (URLs, domains, paths, e-mail).
_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’")
_SPACED_SLASH = re.compile(r"\s*/\s*")
_SPACED_COLON = re.compile(r"\s*:/+")
_SPACED_DOT = re.compile(r"(?<=\w)\.\s+(?=[a-z0-9])")
_ADDRESS_HINTS = ("/", "@", "www.", ".com", ".org", ".net", ".gov", ".edu", ".py", ".htm")


def ordinary_words(text: str) -> set[str]:
    """Words a translation is expected to change: lower-case, outside quotes and addresses.

    Names, brands and acronyms are capitalised and legitimately survive translation - an author
    list or "Planet eBook.com" came back unchanged and correct, and was taken for untranslated
    text by a check that counted every word.
    """
    text = _QUOTED.sub(" ", _MARKER.sub("", text))
    # Text extraction spaces addresses out ("https: // thinkpython. com/ code/"); put them back
    # together so they are recognised as one address rather than as ordinary words. A dot
    # followed by a lower-case letter is not the end of a sentence.
    text = _SPACED_SLASH.sub("/", text)
    text = _SPACED_COLON.sub("://", text)
    text = _SPACED_DOT.sub(".", text)
    kept = [
        token for token in text.split()
        if not any(hint in token.casefold() for hint in _ADDRESS_HINTS)
    ]
    return {w for w in _WORD.findall(" ".join(kept)) if w.islower()}


def is_identical(source: str, reply: str) -> bool:
    return bool(reply) and normalised(reply) == normalised(source)


def is_copy(source: str, reply: str) -> bool:
    """The reply is the source, verbatim or lightly edited - still in the source language.

    Judged on ordinary words (see `ordinary_words`): when most of the reply's ordinary words are
    also the source's, the words a translation must change did not change. Beyond identity this
    catches book page 251, which came back in English with its recognition noise corrected
    ("co s n thn" -> "communicate with"). A reply with too few ordinary words to judge - a name,
    a label, a code - is not called a copy here; `is_identical` still reports that it came back
    unchanged, for a caller that wants to ask again.
    """
    if not reply:
        return False
    words = ordinary_words(reply)
    if len(words) < COPY_MIN_WORDS:
        return False
    if is_identical(source, reply):
        return True
    return len(words & ordinary_words(source)) / len(words) > COPY_SHARE


_DIGITS = re.compile(r"\d+")


def drops_numbers(source: str, reply: str) -> bool:
    """True when a number in the source is missing from the reply.

    A section number, a page reference or a value is content, and the model can lose one without
    anything else looking wrong - NIST's contents came back as "Program Politikasinin Temel
    Bilesenleri .... 27" for "5.2.1 Basic Components of Program Policy .... 27". Compared as digit
    groups, so a decimal the target language writes with a comma ("3,14" for "3.14") still matches.
    """
    have = Counter(_DIGITS.findall(_MARKER.sub("", reply)))
    need = Counter(_DIGITS.findall(_MARKER.sub("", source)))
    return any(have[digits] < count for digits, count in need.items())
