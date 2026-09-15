"""Detects a reply that is the source text handed straight back.

`Segment.translated` is `bool(target)`, so a model that returns its input verbatim scores as a
successful translation and the untranslated text is written into the output document with nothing
flagged. Measured, not hypothetical: on a 60-segment passage of Alice, gemma-4-e2b returned 10
segments untouched - full English sentences - whenever context_before/context_after were sent.
gemma-4-e4b did not do it at all, which is the point: this cannot be fixed by choosing a model
or by dropping context, only by noticing it.

Deliberately conservative, because identity is sometimes correct. A part number, a heading like
"Form W-4" or a bare proper noun should come back unchanged, and protection already answers
data-only segments with their own source on purpose. Only a segment long enough that an
identical translation is implausible is flagged.
"""

from __future__ import annotations

import re

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import is_data_only

#: Below this many words, an identical reply is more likely correct than broken - names,
#: headings and codes all translate to themselves. On the measured passage every genuine
#: passthrough ran to a full sentence and every legitimate identity was two words or fewer.
MIN_WORDS = 4


def _normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def is_passthrough(segment: Segment) -> bool:
    if not segment.target or is_data_only(segment.source):
        return False
    if len(segment.source.split()) < tunables.get("passthrough.min_words"):
        return False
    return _normalised(segment.target) == _normalised(segment.source)


def flag_passthrough(segments: list[Segment]) -> int:
    """Mark every segment the model handed back unchanged. Returns how many."""
    found = 0
    for segment in segments:
        if is_passthrough(segment):
            segment.needs_review = True
            segment.review_reason = "model metni çevirmeden aynen geri verdi"
            found += 1
    return found


def flag_untranslated(segments: list[Segment]) -> int:
    """Mark every segment whose reply never arrived. Returns how many.

    The other half of `flag_passthrough`, and the one that actually bit: a segment with no
    `target` is not written as an empty box, it keeps the block's existing source text, so the
    output document silently contains a paragraph in the wrong language. On six real pages of
    `computer-systems-Architecture.pdf` seventeen segments came back this way and the only sign
    was the count `193/210`.

    Data-only segments are excluded for the same reason `is_passthrough` excludes them:
    protection answers those without a request by design, so an unchanged target there is
    correct and flagging it would bury the genuine losses.
    """
    found = 0
    for segment in segments:
        if segment.target or is_data_only(segment.source):
            continue
        found += 1
        segment.needs_review = True
        # Whatever flagged this first (low OCR confidence, a lost marker) knows more about why.
        if not segment.review_reason:
            segment.review_reason = "çeviri dönmedi, kaynak metin olduğu gibi kaldı"
    return found
