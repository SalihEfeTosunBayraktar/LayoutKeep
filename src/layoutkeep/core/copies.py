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


def is_identical(source: str, reply: str) -> bool:
    return bool(reply) and normalised(reply) == normalised(source)


def is_copy(source: str, reply: str) -> bool:
    """The reply is the source, verbatim or lightly edited - still in the source language.

    Beyond identity it catches book page 251, which came back in English with its recognition
    noise corrected ("co s n thn" -> "communicate with").
    """
    if not reply:
        return False
    if is_identical(source, reply):
        return True
    words = content_words(reply)
    if len(words) < COPY_MIN_WORDS:
        return False
    return len(words & content_words(source)) / len(words) >= COPY_SHARE
