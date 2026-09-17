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


#: The most frequent function words of each language this can judge. They carry no subject matter,
#: so any running text in a language is dense with its own and nearly free of another's - which is
#: what makes a reply in the wrong language visible whatever it is about.
_FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(["ve", "bir", "bu", "için", "ile", "da", "de", "olan", "olarak", "gibi", "daha", "çok", "en", "ancak", "ya", "veya", "ki", "ama", "her", "şu", "o"]),
    "en": frozenset(["the", "and", "of", "to", "is", "in", "that", "with", "for", "are", "this", "which", "by", "be", "as", "on", "an", "or", "from", "it", "was", "were"]),
    "de": frozenset(["der", "die", "das", "und", "ist", "sind", "nicht", "mit", "von", "zu", "den", "ein", "eine", "im", "auf", "für", "sich", "dem", "des", "ich"]),
    "fr": frozenset(["le", "la", "les", "et", "est", "des", "une", "un", "du", "que", "pour", "dans", "pas", "sur", "au", "qui", "ne", "se"]),
    "es": frozenset(["el", "la", "los", "las", "y", "es", "que", "en", "un", "una", "por", "con", "para", "del", "se", "no", "lo"]),
    "it": frozenset(["il", "la", "le", "e", "è", "che", "di", "un", "una", "per", "con", "del", "della", "non", "si", "gli"]),
    "pt": frozenset(["o", "a", "os", "as", "e", "é", "que", "de", "um", "uma", "para", "com", "do", "da", "não", "se", "em"]),
    "nl": frozenset(["de", "het", "en", "is", "een", "van", "dat", "die", "in", "op", "met", "voor", "niet", "zijn", "te"]),
}

#: A reply needs this many words before its function words say anything.
_LANGUAGE_MIN_WORDS = 6

#: Share of a reply's words that must be another language's function words, and outnumber the
#: target's, before the reply is called that language.
_LANGUAGE_SHARE = 0.12


def wrong_language(reply: str, target_lang: str) -> str | None:
    """The language a reply is actually in, when it is clearly not `target_lang`; else None.

    Only languages with a profile are judged, and an unknown target is never judged. Quoted text
    and addresses are left out first, so a translation that keeps an English program output or a
    URL is not taken for English.
    """
    target = _FUNCTION_WORDS.get(target_lang.split("-")[0].casefold())
    if target is None:
        return None
    text = _QUOTED.sub(" ", _MARKER.sub("", reply))
    # A suffix joined by an apostrophe ("Latince'deki", "16.1'e") is part of its word: split off,
    # "de" and "e" read as Dutch and Italian function words.
    words = [
        w.casefold() for token in text.split()
        if not any(hint in token.casefold() for hint in _ADDRESS_HINTS)
        for w in re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", token)
    ]
    if len(words) < _LANGUAGE_MIN_WORDS:
        return None
    own = sum(w in target for w in words) / len(words)
    best, best_share = None, own
    for lang, profile in _FUNCTION_WORDS.items():
        if profile is target:
            continue
        hits = [w for w in words if w in profile]
        share = len(hits) / len(words)
        # At least two different function words: one alone ("ne", which French also has) is a
        # coincidence, not a language.
        if len(set(hits)) >= 2 and share >= _LANGUAGE_SHARE and share > best_share:
            best, best_share = lang, share
    return best
