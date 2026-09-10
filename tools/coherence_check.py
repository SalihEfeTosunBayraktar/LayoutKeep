"""Measure whether translation holds together across consecutive segments.

Translating a document one block at a time risks failures a single-sentence test never shows:
a term rendered differently each time it appears, a back-reference that no longer resolves, and
batching, which puts neighbouring segments into separate requests entirely.

Three things are under test here, and each is a decision the project has already made without
evidence:

  * `context_before` / `context_after` have been sent since the beginning. They roughly triple
    the prompt, so if they do not improve consistency they are pure expense.
  * Batch size adapts at run time. Neighbouring segments can land in different requests, and
    nobody has checked what that does to terminology.
  * Both were justified by reasoning, not measurement.

METHOD. Aligning English words to Turkish ones is not something to attempt honestly - Turkish is
agglutinative, so one source word maps to a stem plus suffixes that vary by case. Instead this
uses a differential: for a source term, compare the words appearing in the targets of segments
that CONTAIN it against those in segments that do not. A word concentrated in the first group is
almost certainly the term's translation. Counting every word in those segments - which an earlier
version of this tool did - mostly measures how common "said" is in dialogue.

Consistency is then how concentrated that evidence is: one dominant rendering means the model
kept its terminology, several competing ones mean it did not.

All three arms are scored over the same term set - the intersection of what each could
measure. An arm that fails to translate a segment loses that term's evidence, and an
earlier run duly compared 0/2 against 0/4 as though that meant something. It did not.

    .venv/Scripts/python.exe tools/coherence_check.py --model google/gemma-4-e4b
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.core.docir import Segment, segments_from_document
from layoutkeep.providers.openai_compat import OpenAICompatProvider
from layoutkeep.readers.epub_reader import read_epub

#: Words too common to say anything about consistency. Kept as prose and split rather than as a
#: list literal: seventy quoted strings are far harder to read and edit than seventy words.
_STOPWORDS = frozenset((  # noqa: SIM905
    "the a an and or but if of to in on at for with as it its is was were be been "
    "that this these those he she they we you i him her them his their your my "
    "not no so then than there here when what which who whom how why "
    "all any some very just only own same too can will would could should "
    "said say says one two do did does done had have has"
).split())

#: Turkish stems that carry no terminological weight - mostly speech verbs and pronouns that
#: saturate dialogue and would otherwise look like every term's translation.
_TARGET_NOISE_WORDS = (
    "dedi diye söyledi söylüyor bunu şunu ile için gibi daha çok ama veya".split()  # noqa: SIM905
)

STEM_LENGTH = 5

#: How many distinct segments a term must appear in before its rendering is worth judging.
#: Measured, not chosen: at two segments the contrast has so few segments to subtract that an
#: unrelated co-occurring word survives it by luck. A real run produced "again -> agzin, nargi"
#: and "three -> inc, boy" that way, and both scored as consistent. At three the same passage
#: kept only the two terms whose candidates were actually right.
MIN_TERM_SEGMENTS = 3


def _stem(word: str) -> str:
    return word.lower()[:STEM_LENGTH]


#: Stemmed, because that is what it is compared against - a noise word longer than STEM_LENGTH
#: would otherwise never match anything and the filter would be silently inert.
_TARGET_NOISE = frozenset(_stem(w) for w in _TARGET_NOISE_WORDS)


def _target_stems(text: str) -> set[str]:
    stems = {_stem(w) for w in re.findall(r"[^\W\d_]{3,}", text, re.UNICODE)}
    return {s for s in stems if s not in _TARGET_NOISE}


def repeated_terms(segments: list[Segment], min_occurrences: int = 3) -> dict[str, int]:
    """Content words appearing often enough that inconsistency would be visible to a reader.

    Proper nouns are excluded even though they repeat constantly. A name is carried across
    unchanged by every model, so it scores as consistent under every condition and tells us
    nothing about whether context helps - it only inflates all the arms equally and hides the
    difference we are trying to see. A word is taken as a proper noun when every one of its
    occurrences is capitalised somewhere other than the start of a sentence.
    """
    counts: Counter[str] = Counter()
    lowercase_seen: set[str] = set()
    for segment in segments:
        for match in re.finditer(r"[A-Za-z][A-Za-z'-]{3,}", segment.source):
            word = match.group(0)
            lowered = word.lower()
            if lowered in _STOPWORDS:
                continue
            counts[lowered] += 1
            if not word[0].isupper():
                lowercase_seen.add(lowered)
    return {
        w: n for w, n in counts.items() if n >= min_occurrences and w in lowercase_seen
    }


@dataclass(slots=True)
class TermResult:
    term: str
    occurrences: int
    #: Candidate renderings, most evidence first: (stem, segments containing it).
    candidates: list[tuple[str, int]]

    @property
    def consistent(self) -> bool:
        """True when one rendering dominates - it appears wherever the term does.

        A term whose translation is present in every segment that uses it was rendered the same
        way each time. A tie between two candidates means the model alternated, so a tie is not
        consistency even when both cover every occurrence.
        """
        if not self.candidates:
            return False
        best = self.candidates[0][1]
        tied = sum(1 for _, n in self.candidates if n == best)
        return tied == 1 and best == self.occurrences


def analyse(segments: list[Segment], terms: dict[str, int]) -> list[TermResult]:
    """Find each term's likely rendering by contrast with segments that do not contain it."""
    results: list[TermResult] = []
    for term in terms:
        with_term = [s for s in segments if term in s.source.lower() and s.target]
        without = [s for s in segments if term not in s.source.lower() and s.target]
        if len(with_term) < MIN_TERM_SEGMENTS:
            continue
        elsewhere: set[str] = set()
        for segment in without:
            elsewhere |= _target_stems(segment.target)

        support: Counter[str] = Counter()
        for segment in with_term:
            for stem in _target_stems(segment.target) - elsewhere:
                support[stem] += 1
        # Only stems seen more than once are evidence; a single appearance is noise.
        candidates = [(s, n) for s, n in support.most_common(4) if n > 1]
        if candidates:
            results.append(TermResult(term, len(with_term), candidates))
    return results


def translate(
    provider: OpenAICompatProvider,
    segments: list[Segment],
    *,
    with_context: bool,
    batch: int | None,
) -> list[Segment]:
    prepared = [
        Segment(
            block_id=s.block_id,
            source=s.source,
            context_before=s.context_before if with_context else "",
            context_after=s.context_after if with_context else "",
        )
        for s in segments
    ]
    kwargs = {} if batch is None else {"max_batch_segments": batch}
    provider_for_run = OpenAICompatProvider(
        base_url=provider.base_url, model=provider.model, **kwargs
    )
    return provider_for_run.translate(prepared, "en", "tr")


ARMS: tuple[tuple[str, bool, int | None], ...] = (
    ("bağlamlı", True, None),
    ("bağlamsız", False, None),
    ("parti=1", True, 1),
)


def measure(segments: list[Segment], terms: dict[str, int]) -> dict[str, TermResult]:
    return {r.term: r for r in analyse(segments, terms)}


def _print_arm(label: str, results: list[TermResult]) -> int:
    good = sum(1 for r in results if r.consistent)
    print()
    print(f"--- {label} ---  tutarlı {good}/{len(results)}")
    for r in results:
        shown = ", ".join(f"{stem}({n})" for stem, n in r.candidates)
        flag = "  " if r.consistent else "<-"
        print(f"  {flag} {r.term:<14} {r.occurrences} segmentte   aday: {shown}")
    return good


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--book", default=str(ROOT / "_artifacts/corpus/pg11.epub"))
    parser.add_argument("--skip", type=int, action="append", default=None,
                        help="passage offset; repeat to measure several passages")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--dump", default=None, metavar="PATH",
                        help="write every arm's translations here as JSON. Worth using: the "
                             "candidate lists say which stems won, not what the model actually "
                             "wrote, and a run costs about twenty minutes to repeat.")
    args = parser.parse_args(argv)

    offsets = args.skip or [200, 400]
    everything = segments_from_document(read_epub(args.book))
    provider = OpenAICompatProvider(base_url=args.base_url, model=args.model)

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    dump: dict[str, dict[str, list[dict[str, str]]]] = {}
    for offset in offsets:
        passage = everything[offset : offset + args.limit]
        terms = repeated_terms(passage)
        print()
        print("=" * 74)
        print(f"pasaj @{offset}: {len(passage)} segment, "
              f"{sum(len(s.source) for s in passage)} karakter, "
              f"{len(terms)} tekrar eden terim", flush=True)

        measured: dict[str, dict[str, TermResult]] = {}
        for label, ctx, batch in ARMS:
            translated = translate(provider, passage, with_context=ctx, batch=batch)
            measured[label] = measure(translated, terms)
            if args.dump:
                dump.setdefault(f"@{offset}", {})[label] = [
                    {"source": s.source, "target": s.target or ""} for s in translated
                ]
            done = sum(1 for s in translated if s.target)
            print(f"  {label:<11} çevrildi {done}/{len(passage)}, "
                  f"ölçülebilir terim {len(measured[label])}", flush=True)

        # Only terms every arm could measure. An arm that fails to translate a segment loses that
        # term's evidence, and scoring arms over different term sets compares nothing: a run
        # where one arm scored 0/2 and another 0/4 is not a result, it is two different questions.
        shared = set.intersection(*(set(m) for m in measured.values())) if measured else set()
        print(f"  --> her kolda ölçülebilen: {len(shared)} terim "
              f"({', '.join(sorted(shared)) or 'yok'})")

        for label, _ctx, _batch in ARMS:
            results = [measured[label][t] for t in sorted(shared)]
            totals[label][0] += _print_arm(label, results)
            totals[label][1] += len(results)

    if args.dump:
        Path(args.dump).write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"çeviriler yazıldı: {args.dump}")

    print()
    print("=" * 74)
    print(f"TOPLAM ({len(offsets)} pasaj, kollar aynı terim kümesi üzerinde)")
    for label, (good, total) in totals.items():
        rate = f"{good / total:.0%}" if total else "-"
        print(f"  {label:<12} tutarlı {good}/{total}  ({rate})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
