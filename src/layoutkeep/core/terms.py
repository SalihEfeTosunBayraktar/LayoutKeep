"""Term candidates from a document: what recurs, so the glossary editor can offer a starting list.

WHY THIS EXISTS: the glossary is the strongest quality lever the pipeline has - a term forced in
the prompt and checked in the output cannot drift - but filling it by hand means reading the
document and noticing what repeats, which is exactly the work a machine should do. BabelDOC offers
automatic term extraction; this is the same idea with a deliberately simple, explainable rule.

WHAT IT IS, HONESTLY: a frequency heuristic, not understanding. It finds phrases that recur in the
document, keeps the ones that look like noun phrases, and hands them to a person to accept or
reject. It does not know what a term *means*, and it will offer useless phrases on a document
whose repeated phrases are boilerplate - which is why the result is a list to edit, never a
glossary applied silently.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from layoutkeep.core import stopwords

#: A word, with what follows an apostrophe kept apart: Turkish writes a name's suffix after one
#: ("Türkiye’nin", "SKA’ların") and English a possessive ("Gutenberg’s"). Split on the apostrophe,
#: the suffix came out as a word of its own and "SKA ların" was offered as a term.
#: Kesme işaretinden sonraki ek ayrı tutulur; öneri kökü verir ("Türkiye’nin" -> "Türkiye").
_WORD = re.compile(r"([^\W\d_][\w-]*)((?:['’]\w*)?)", re.UNICODE)

#: A phrase shorter than this many characters is not worth offering (a glossary of two-letter
#: entries is noise).
_MIN_CHARS = 4


@dataclass(frozen=True)
class Candidate:
    """One offered term: the phrase and how often the document used it."""

    phrase: str
    count: int

    @property
    def score(self) -> float:
        """Frequency weighted by length: a recurring three-word phrase is worth more attention
        than a recurring single word, which is usually just the document's topic."""
        return self.count * (1.0 + 0.35 * (self.phrase.count(" ") ))


def _tokens(text: str) -> tuple[list[str], list[bool]]:
    """The words of `text`, and for each whether a suffix followed it after an apostrophe."""
    pairs = _WORD.findall(text)
    return [word for word, _ in pairs], [bool(suffix) for _, suffix in pairs]


def _phrases(text: str, max_words: int, edges: frozenset[str], inside: frozenset[str]) -> list[str]:
    words, suffixed = _tokens(text)
    lowered = [word.casefold() for word in words]
    found: list[str] = []
    for start in range(len(words)):
        for length in range(2, max_words + 1):
            window = lowered[start : start + length]
            if len(window) < length:
                break
            if window[0] in edges or window[-1] in edges:
                continue
            if any(len(word) < 3 for word in window) or inside.intersection(window):
                continue
            # A suffix may only close the phrase: "Türkiye’nin ulusal" is not in the text as
            # "Türkiye ulusal". / Ek yalnız öbeğin sonunda olabilir.
            if any(suffixed[start : start + length - 1]):
                continue
            found.append(" ".join(words[start : start + length]))
        # Single words too: a long word that recurs is a term in its own right.
        if (len(words[start]) >= _MIN_CHARS and lowered[start] not in edges
                and lowered[start] not in inside):
            found.append(words[start])
    return found


def _lists(texts: list[str], languages: Iterable[str] | None) -> tuple[frozenset[str], frozenset[str]]:
    """The function-word lists for the given languages, or for the language the text reads as.

    Verilen dillerin ya da metinden tahmin edilen dilin sözcük listeleri.
    """
    codes = [code for code in (languages or ()) if code]
    if not any(code.strip().lower() in stopwords.FUNCTION_WORDS for code in codes):
        guessed = stopwords.guess(word.casefold() for text in texts for word in _tokens(text)[0])
        codes = [guessed] if guessed else []
    return stopwords.lists_for(codes)


def candidates(
    texts: list[str],
    *,
    minimum_count: int = 3,
    limit: int = 40,
    max_words: int = 3,
    exclude: set[str] | None = None,
    languages: Iterable[str] | None = None,
) -> list[Candidate]:
    """Rank the phrases that recur across `texts`, most useful first.

    `exclude` holds phrases already in the glossary (case-insensitive): offering a term the user
    has already decided about wastes their attention. `languages` picks the function-word lists;
    without a known one the language is guessed from the text (`core/stopwords.py`).
    """
    already = {phrase.strip().casefold() for phrase in (exclude or set()) if phrase.strip()}
    edges, inside = _lists(texts, languages)
    counts: Counter[str] = Counter()
    for text in texts:
        for phrase in _phrases(text, max_words, edges, inside):
            key = phrase.casefold()
            if key in already or len(phrase) < _MIN_CHARS:
                continue
            counts[phrase] += 1

    ranked = [
        Candidate(phrase=phrase, count=count)
        for phrase, count in counts.items()
        if count >= minimum_count
    ]
    ranked.sort(key=lambda item: (item.score, len(item.phrase), item.phrase), reverse=True)
    return ranked[:limit]


def suggest_from_document(
    document, *, limit: int = 40, exclude: set[str] | None = None, language: str | None = None
):
    """Candidates from a DocIR document: every translatable block's text, in reading order.

    `language` is the source language when the caller knows it; else the document's own, else a
    guess from its text. / Kaynak dil biliniyorsa verilir; yoksa belgeninki, o da yoksa tahmin.
    """
    texts = [
        block.text
        for _page, block in document.iter_blocks()
        if getattr(block, "translatable", True) and block.text.strip()
    ]
    known = language or getattr(document, "source_lang", None)
    return candidates(texts, limit=limit, exclude=exclude, languages=[known] if known else None)
