"""Size estimates for a translation job: characters, tokens, and how far along it is.

Two things this exists for:

* Telling the user up front how big the job is, so they can judge the wait and, on a paid
  endpoint, the cost.
* Measuring progress by characters rather than by segment count. Segments run from a
  five-character heading to a five-hundred-character paragraph, so "half the segments" can mean
  anywhere from a fifth to four fifths of the actual work. Counting characters is not perfect
  either, but it is much closer to the truth.

The token figures are estimates from character counts, not tokeniser output. Every provider
tokenises differently and we deliberately do not depend on one. Where a provider reports real
usage, prefer that and use these only until it does.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from layoutkeep.core.docir import Segment

#: Average characters per token, by language, for the BPE tokenisers the common models use.
#: Turkish sits lower than English: it is agglutinative, so words split into more pieces, and
#: its non-ASCII letters cost extra bytes in a byte-level BPE.
_CHARS_PER_TOKEN: dict[str, float] = {
    "en": 4.0,
    "de": 3.6,
    "fr": 3.7,
    "es": 3.8,
    "it": 3.8,
    "pt": 3.8,
    "nl": 3.7,
    "pl": 3.0,
    "tr": 3.0,
}
_CHARS_PER_TOKEN_DEFAULT = 3.5

#: How much longer the translation is expected to be than the source, by target language.
#:
#: `tr` is measured, the rest are still literature estimates. The Turkish figure came out at
#: 0.93 - the translation is SHORTER than the English, not 15% longer as the literature led us
#: to assume. Turkish is agglutinative, so a single word often carries what English spreads over
#: several. See docs/MEASUREMENTS.md for the run.
#:
#: The mean is not the whole story. Individual blocks ranged from 0.64x to 1.40x, so the fitting
#: engine still matters: a minority of blocks overflow badly even though the average shrinks.
#: This is a variance problem, not the systematic expansion problem we designed against.
_EXPANSION: dict[str, float] = {
    "tr": 0.93,  # measured, EN->TR literary prose, gemma-4-e4b, 40 segments
    "de": 1.30,
    "es": 1.20,
    "fr": 1.20,
    "it": 1.15,
    "pt": 1.20,
    "nl": 1.20,
    "pl": 1.15,
    "en": 1.00,
}
_EXPANSION_DEFAULT = 1.15


def chars_per_token(lang: str | None) -> float:
    return _CHARS_PER_TOKEN.get((lang or "").lower(), _CHARS_PER_TOKEN_DEFAULT)


def expansion_ratio(target_lang: str | None) -> float:
    return _EXPANSION.get((target_lang or "").lower(), _EXPANSION_DEFAULT)


@dataclass(slots=True)
class JobEstimate:
    """What a job is expected to cost, before it runs."""

    segments: int
    source_chars: int
    input_tokens: int
    output_tokens: int
    #: The expansion ratio used, so a caller can say which number it assumed.
    assumed_expansion: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def estimate_job(
    segments: Sequence[Segment],
    src_lang: str | None,
    tgt_lang: str | None,
    *,
    include_context: bool = True,
) -> JobEstimate:
    """Estimate the size of translating `segments`.

    `include_context` counts the neighbouring-block context that travels with each segment. It
    is part of what the model reads and, on a metered endpoint, part of what gets billed - so
    leaving it out would understate the cost of the very feature that improves consistency.
    """
    source_chars = sum(len(s.source) for s in segments)
    read_chars = source_chars
    if include_context:
        read_chars += sum(len(s.context_before) + len(s.context_after) for s in segments)

    ratio = expansion_ratio(tgt_lang)
    return JobEstimate(
        segments=len(segments),
        source_chars=source_chars,
        input_tokens=round(read_chars / chars_per_token(src_lang)),
        output_tokens=round(source_chars * ratio / chars_per_token(tgt_lang)),
        assumed_expansion=ratio,
    )


def progress_by_chars(segments: Sequence[Segment]) -> tuple[int, int]:
    """Return (characters translated, characters total).

    Counted on the source side: a segment contributes its full source length once it has a
    translation. Measuring the target instead would make the bar jump around as the translation
    turned out longer or shorter than the original.
    """
    total = sum(len(s.source) for s in segments)
    done = sum(len(s.source) for s in segments if s.translated)
    return done, total


def measured_expansion(segments: Sequence[Segment]) -> float | None:
    """The real target/source length ratio over the segments translated so far.

    None until something has been translated. This is the number that should eventually replace
    the estimate in `_EXPANSION`, and the one the fitting engine's thresholds depend on.
    """
    src = sum(len(s.source) for s in segments if s.translated)
    tgt = sum(len(s.target) for s in segments if s.translated)
    return tgt / src if src else None
