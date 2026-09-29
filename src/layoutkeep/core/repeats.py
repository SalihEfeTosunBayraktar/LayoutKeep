"""One source text, one translation - across the whole document.

WHY THIS EXISTS. `providers/dedupe.py` stops the same text being translated twice in a run, so
its occurrences cannot disagree. This is the net under it: a document can still hold the same
source text with two different translations - a resumed run wrote some of it earlier, a memory
entry answered part of it, or the repair ladder re-asked one occurrence with a different result.
Measured on the recorded held-out runs: irs_p505 came back with 80 such groups (272 segments),
irs_i1040gi 19 (128), arXiv 2609.19145 21 (76), cookbook_1907 8 (18).

The reader notices: IRS Form 1040's instructions word "Married filing separately" three ways in
one document and "Head of household" two, and every one of those rows is correct on its own.

WHAT IT DOES. Groups the translated segments by their source text (same normalisation and same
three-word floor as the dedupe pass), and where a group holds more than one translation, rewrites
the minority to the majority. Nothing is invented and nothing is re-asked: every rewrite is a
translation this document already produced for that exact source, so the sweep cannot introduce a
wrong translation - only remove a disagreement. A variant that loses one of the source's numbers is
never chosen while a variant that keeps them exists, and ties go to the one that appears first.

It reports what it did, so a run says how much of the document it had to make agree with itself.
"""

from __future__ import annotations

from collections import Counter

from layoutkeep.core.copies import drops_numbers
from layoutkeep.core.docir import Segment

#: Fewer words than this and two texts are not the same text: "where" and "ours" legitimately
#: translate differently in different sentences, so they are never made to agree.
MIN_WORDS = 3


def share_key(source: str) -> str | None:
    """The key two segments share when they are the same text. None when they must not be shared.

    Whitespace and case are ignored, so a text that a page broke across two lines and the same
    text set on one line are one text.
    """
    text = " ".join(source.split())
    if len(text.split()) < MIN_WORDS:
        return None
    return text.casefold()


#: The most rewrites reported in full; the count is always complete.
_EXAMPLES = 3


def _variant(text: str) -> str:
    return " ".join(text.split())


def unify_repeats(segments: list[Segment], target_lang: str = "") -> dict[str, object]:
    """Make each repeated source text carry one translation. `segments` is updated in place.

    Returns {"groups": how many repeated texts disagreed, "rewritten": how many segments changed,
    "examples": a few (source, kept) pairs for the log}.
    """
    groups: dict[str, list[Segment]] = {}
    for seg in segments:
        if not seg.target:
            continue
        key = share_key(seg.source)
        if key is None:
            continue
        groups.setdefault(key, []).append(seg)

    rewritten = 0
    disagreeing = 0
    examples: list[tuple[str, str]] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        counts = Counter(_variant(seg.target) for seg in group)
        if len(counts) < 2:
            continue

        disagreeing += 1
        source = group[0].source
        keeping_numbers = [v for v in counts if not drops_numbers(source, v, target_lang)]
        candidates = keeping_numbers or list(counts)
        first_seen: dict[str, int] = {}
        for index, seg in enumerate(group):
            first_seen.setdefault(_variant(seg.target), index)
        chosen = max(candidates, key=lambda v: (counts[v], -first_seen[v]))

        for seg in group:
            if _variant(seg.target) != chosen:
                seg.target = chosen
                rewritten += 1
        if len(examples) < _EXAMPLES:
            examples.append((_variant(source)[:70], chosen[:70]))

    return {"groups": disagreeing, "rewritten": rewritten, "examples": examples}
