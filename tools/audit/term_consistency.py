"""Aynı kaynak terim, kaç farklı çeviri? Haritanın vaadi tutarlılık, ölçüsü de bu.

WHY: the topic map puts "This part is about: ..." in front of every segment, and the claim was always
that it keeps a book's terms consistent from part to part. "Kaliteye etkisi ölçülmemiştir" was the
honest note while nothing measured it; this is the measurement. For each proper noun that appears in
more than one block of the source, count how many distinct target forms the run produced. Fewer
distinct forms for the same source term is the map doing its job.

Reads two `.lkproj` files (or two directories holding one) and prints the comparison. No model calls,
no network: it only looks at what the runs already wrote.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from layoutkeep.core.docir import load_project  # noqa: E402

#: A proper noun: a capitalised word of two or more letters that is not at the start of a sentence.
_TOKEN = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z]{2,})\b")


def _segments(project: Path) -> list[tuple[str, str]]:
    doc = load_project(project)
    pairs: list[tuple[str, str]] = []
    for page in doc.pages:
        for block in page.blocks:
            source = (block.source_text or "").strip()
            target = (block.text or "").strip()
            if source:
                pairs.append((source, target))
    return pairs


def _term_forms(pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
    """For each source proper noun appearing in 2+ blocks, the set of target forms seen."""
    forms: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for source, target in pairs:
        for term in set(_TOKEN.findall(source)):
            counts[term] += 1
            # The target form is the run's own choice; record what it wrote for the same block.
            for candidate in _TOKEN.findall(target):
                forms[term].add(candidate)
    return {term: forms[term] for term, n in counts.items() if n >= 2 and forms.get(term)}


def compare(without: Path, with_map: Path) -> int:
    base = _term_forms(_segments(without))
    mapped = _term_forms(_segments(with_map))
    shared = sorted(set(base) | set(mapped))
    print(f"{'terim':24s} {'haritasiz':>10s} {'haritali':>10s}")
    better = worse = 0
    for term in shared:
        a, b = len(base.get(term, ())), len(mapped.get(term, ()))
        flag = ""
        if a and b and b < a:
            better += 1
            flag = "  <- daha tutarli"
        elif a and b and b > a:
            worse += 1
            flag = "  <- daha dagilmis"
        print(f"{term:24s} {a:10d} {b:10d}{flag}")
    print(f"\nterim: {len(shared)} | haritali daha tutarli: {better} | daha dagilmis: {worse}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("kullanim: term_consistency.py <haritasiz.lkproj> <haritali.lkproj>")
        return 2
    return compare(Path(argv[1]), Path(argv[2]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
