"""Is one source term translated one way throughout the document? The consistency bar, measured.

WHY THIS EXISTS: the user's bar is "above 90% quality AND consistency". The first version of this tool
counted every capitalised word in a target block as a "form" of each proper noun in its source - it
could not tell a term's translation from the rest of the sentence, and proper nouns are mostly not
translated at all, so it measured nothing (and "16 of 16 equal" closed the topic map on that basis,
D-007). This version asks what each occurrence was actually translated as.

Method: the recurring terms of the source (`core/terms.candidates`, the same list the glossary editor
offers) are located in the translated blocks; for every occurrence the judge model (DeepSeek through
Hermes, never the model under test) names the target words that render the term, in dictionary form
so Turkish suffixes do not count as different choices. A term's consistency is the share of its
occurrences that use its most common rendering; the document's is the same share over all occurrences.

    python tools/audit/term_consistency.py _artifacts/bench/<commit>     # writes CONSISTENCY.md there
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))

# The judge call and the marker cleaning are shared with quality_judge, so both bars read alike.
from quality_judge import LANG, _ask, _plain

from layoutkeep.core.docir import load_project
from layoutkeep.core.terms import candidates

TERMS = 15
PER_TERM = 6

PROMPT = """You check terminology consistency in a translation. Do not use any tools; answer only.
Source language: {src}. Target language: {dst}.

For each term below you get the source segments where it occurs and their translations. For every
occurrence, give the target-language words that translate THAT term, in dictionary form (no case or
possessive suffixes, singular), lowercase. Use null when the translation left the term out. If the
term was kept unchanged (a name), give it as is.

Reply with ONLY a JSON object: {{"<term>": ["rendering or null", ...], ...}} with one entry per
occurrence, in the order given.

{items}"""


def _pairs(run: Path) -> list[tuple[str, str]]:
    pairs = []
    for project in sorted((run / "run" / "out").glob("*.lkproj")):
        doc = load_project(project)
        for page in doc.pages:
            for block in page.blocks:
                source, target = _plain(block.source_text), _plain(block.text)
                if source and target and source != target:
                    pairs.append((source, target))
    return pairs


def _occurrences(term: str, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
    return [pair for pair in pairs if pattern.search(pair[0])][:PER_TERM]


def measure(run: Path, src: str, dst: str) -> dict:
    pairs = _pairs(run)
    terms = [c.phrase for c in candidates([s for s, _ in pairs], minimum_count=2, limit=TERMS * 2)]
    found = {term: occ for term in terms if len(occ := _occurrences(term, pairs)) >= 2}
    found = dict(list(found.items())[:TERMS])
    if not found:
        return {"terms": {}, "consistent": 0, "occurrences": 0}

    def one(chunk: list[str]) -> dict:
        items = "\n\n".join(
            f"TERM: {term}\n" + "\n".join(
                json.dumps({"source": s[:600], "target": t[:800]}, ensure_ascii=False) for s, t in found[term]
            )
            for term in chunk
        )
        reply = _ask(PROMPT.format(src=LANG[src], dst=LANG[dst], items=items))
        start, end = reply.find("{"), reply.rfind("}")
        try:
            return json.loads(reply[start : end + 1]) if start >= 0 else {}
        except json.JSONDecodeError:
            return {}

    names = list(found)
    chunks = [names[i : i + 5] for i in range(0, len(names), 5)]
    renderings: dict = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for part in pool.map(one, chunks):
            renderings.update(part)
    # A chunk that timed out or came back unreadable leaves its terms out; ask those one at a time,
    # so one hard term costs itself and not the four asked beside it.
    missing = [[term] for term in names if term not in renderings]
    if missing:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for part in pool.map(one, missing):
                renderings.update(part)

    per_term = {}
    for term in names:
        forms = [str(f).strip().casefold() for f in renderings.get(term) or [] if f]
        if len(forms) < 2:
            continue
        top, count = Counter(forms).most_common(1)[0]
        per_term[term] = {"forms": dict(Counter(forms)), "top": top, "share": count / len(forms)}
    consistent = sum(max(v["forms"].values()) for v in per_term.values())
    occurrences = sum(sum(v["forms"].values()) for v in per_term.values())
    return {"terms": per_term, "consistent": consistent, "occurrences": occurrences}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bench", type=Path)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()

    totals: dict[str, list[int]] = {}
    lines = [f"# Consistency `{args.bench.name}`", "",
             ("Share of a recurring term's occurrences that use its most common rendering "
              "(judged by DeepSeek v4.1 flash, dictionary forms)."), "",
             "| source | dir | terms | occurrences | consistent |", "|---|---|---|---|---|"]
    for run in sorted(p for p in args.bench.iterdir() if p.is_dir()):
        if args.only and run.name not in args.only:
            continue
        meta = run / "bench.json"
        if not meta.exists():
            continue
        src, dst = json.loads(meta.read_text(encoding="utf-8"))["direction"].split("->")
        result = measure(run, src, dst)
        (run / "consistency.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        occ, ok = result["occurrences"], result["consistent"]
        totals.setdefault(f"{src}->{dst}", [0, 0])
        totals[f"{src}->{dst}"][0] += ok
        totals[f"{src}->{dst}"][1] += occ
        share = f"{ok / occ:.0%}" if occ else "-"
        lines.append(f"| {run.name} | {src}->{dst} | {len(result['terms'])} | {occ} | {share} |")
        print(f"{run.name:22} {src}->{dst}  terms {len(result['terms'])}  {share}", flush=True)
    for direction, (ok, occ) in sorted(totals.items()):
        if occ:
            lines.append(f"| **{direction} overall** | | | {occ} | **{ok / occ:.1%}** |")
    out = args.bench / "CONSISTENCY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
