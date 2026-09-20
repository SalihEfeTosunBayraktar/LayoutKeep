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
from dataclasses import dataclass

#: Words that cannot begin or end a candidate phrase. Deliberately short: a long list of English
#: stopwords would be wrong for the other languages this project reads, and the rule that matters
#: (a phrase must not start or end on a function word) survives a short one.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by", "as", "at",
    "is", "are", "was", "were", "be", "been", "that", "this", "these", "those", "it", "its",
    "from", "but", "not", "no", "if", "then", "than", "so", "such", "which", "who", "whom",
    "ve", "bir", "ile", "için", "olarak", "bu", "şu", "da", "de", "ki", "mi", "veya", "ya",
    "der", "die", "das", "und", "oder", "für", "mit", "von", "zu", "ist", "sind",
}

_WORD = re.compile(r"[^\W\d_][\w'-]*", re.UNICODE)

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


def _phrases(text: str, max_words: int) -> list[str]:
    words = _WORD.findall(text)
    lowered = [word.casefold() for word in words]
    found: list[str] = []
    for start in range(len(words)):
        for length in range(2, max_words + 1):
            window = lowered[start : start + length]
            if len(window) < length:
                break
            if window[0] in _STOPWORDS or window[-1] in _STOPWORDS:
                continue
            if any(len(word) < 3 for word in window):
                continue
            found.append(" ".join(words[start : start + length]))
        # Single words too: a long word that recurs is a term in its own right.
        if len(words[start]) >= _MIN_CHARS and lowered[start] not in _STOPWORDS:
            found.append(words[start])
    return found


def candidates(
    texts: list[str],
    *,
    minimum_count: int = 3,
    limit: int = 40,
    max_words: int = 3,
    exclude: set[str] | None = None,
) -> list[Candidate]:
    """Rank the phrases that recur across `texts`, most useful first.

    `exclude` holds phrases already in the glossary (case-insensitive): offering a term the user
    has already decided about wastes their attention.
    """
    already = {phrase.strip().casefold() for phrase in (exclude or set()) if phrase.strip()}
    counts: Counter[str] = Counter()
    for text in texts:
        for phrase in _phrases(text, max_words):
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


def suggest_from_document(document, *, limit: int = 40, exclude: set[str] | None = None):
    """Candidates from a DocIR document: every translatable block's text, in reading order."""
    texts = [
        block.text
        for _page, block in document.iter_blocks()
        if getattr(block, "translatable", True) and block.text.strip()
    ]
    return candidates(texts, limit=limit, exclude=exclude)
