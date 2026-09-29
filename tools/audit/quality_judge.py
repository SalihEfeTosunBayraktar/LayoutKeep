"""How good is the translation, not only how complete? A stronger model scores a sample of segments.

WHY THIS EXISTS: L1-L10 catch loss - a block left in English, a number dropped, text over text. None of
them says whether a translated sentence is right. The user's bar is "above 90% quality and consistency
in both directions", and that needs a quality number. This is the standard way to get one without a
human panel: an MQM-style judgement by a model stronger than the one that translated.

Scoring (per segment, 0-100, MQM-lite): start at 100; each CRITICAL error -25 (meaning changed,
content omitted or added, left untranslated, wrong language), each MAJOR -10 (wrong term, grammar that
hurts understanding, a name or number mangled), each MINOR -2 (style, punctuation, awkward word
order). A segment scoring 80 or more is "acceptable" - usable without a translator touching it.

The judge is the user's DeepSeek through Hermes (`hermes -z`, a fresh session each call), never the
model under test. Segments are sampled deterministically (every block of 30+ characters, evenly spaced,
up to `--per-source`), sent 20 at a time with their source, and the reply is a JSON list.

    python tools/audit/quality_judge.py _artifacts/bench/<commit>          # writes QUALITY.md there
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.core.docir import load_project

HERMES = str(Path.home() / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe")
JUDGE = ["-m", "deepseek-v4.1-flash", "--provider", "opencode-go"]
LANG = {"en": "English", "tr": "Turkish", "de": "German"}
BATCH = 20
ACCEPTABLE = 80
_MARKER = re.compile(r"</?\d+>")

PROMPT = """You are a professional translation quality evaluator (MQM). Do not use any tools; answer only.
Source language: {src}. Target language: {dst}. The segments come from a document translated
block by block; judge each target against its source only.

For each segment start at 100 and subtract: CRITICAL -25 (meaning changed, content omitted or added,
left untranslated, wrong language), MAJOR -10 (wrong term, grammar that hurts understanding, a name
or number mangled), MINOR -2 (style, punctuation, awkward order). Minimum 0. Text that should stay as
is (names, code, formulas, references) is correct when kept.

Reply with ONLY a JSON array, one object per segment, same ids:
[{{"id": 0, "score": 94, "errors": ["MINOR: ..."]}}, ...]

Segments:
{items}"""


def _plain(text: str) -> str:
    return _MARKER.sub("", text or "").strip()


def sample(run: Path, per_source: int) -> list[tuple[str, str]]:
    pairs = []
    for project in sorted((run / "run" / "out").glob("*.lkproj")):
        doc = load_project(project)
        for page in doc.pages:
            for block in page.blocks:
                source, target = _plain(block.source_text), _plain(block.text)
                if len(source) >= 30 and target:
                    pairs.append((source, target))
    if len(pairs) <= per_source:
        return pairs
    step = len(pairs) / per_source
    return [pairs[int(i * step)] for i in range(per_source)]


#: One judge call's limit. A hung call used to raise TimeoutExpired after 900 s and take the whole
#: measurement with it (arm C's consistency pass died twice on one arXiv term); now it is an empty
#: answer, which the callers treat as "not judged" and retry smaller.
ASK_TIMEOUT_S = 300


def _ask(prompt: str) -> str:
    try:
        proc = subprocess.run(
            [HERMES, "-z", prompt, *JUDGE], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=ASK_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print("   judge call timed out - left unjudged", flush=True)
        return ""
    return proc.stdout


def _parse(reply: str) -> list[dict]:
    start, end = reply.find("["), reply.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        items = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [item for item in items if isinstance(item, dict) and "id" in item and "score" in item]


def judge(pairs: list[tuple[str, str]], src: str, dst: str) -> list[dict]:
    batches = [pairs[i : i + BATCH] for i in range(0, len(pairs), BATCH)]

    def one(batch: list[tuple[str, str]]) -> list[dict]:
        items = "\n".join(
            json.dumps({"id": i, "source": s[:1200], "target": t[:1500]}, ensure_ascii=False)
            for i, (s, t) in enumerate(batch)
        )
        scored = _parse(_ask(PROMPT.format(src=LANG[src], dst=LANG[dst], items=items)))
        by_id = {int(item["id"]): item for item in scored if str(item["id"]).isdigit()}
        return [
            {"source": s, "target": t, **by_id[i]} for i, (s, t) in enumerate(batch) if i in by_id
        ]

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [row for rows in pool.map(one, batches) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bench", type=Path, help="a bench directory, _artifacts/bench/<commit>")
    parser.add_argument("--per-source", type=int, default=40)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()

    results: dict[str, dict] = {}
    for run in sorted(p for p in args.bench.iterdir() if p.is_dir()):
        if args.only and run.name not in args.only:
            continue
        meta_file = run / "bench.json"
        if not meta_file.exists():
            continue
        src, dst = json.loads(meta_file.read_text(encoding="utf-8"))["direction"].split("->")
        pairs = sample(run, args.per_source)
        if not pairs:
            continue
        rows = judge(pairs, src, dst)
        (run / "quality.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        scores = [float(row["score"]) for row in rows]
        results[run.name] = {
            "direction": f"{src}->{dst}", "sampled": len(pairs), "judged": len(scores),
            "mean": sum(scores) / len(scores) if scores else 0.0,
            "acceptable": sum(s >= ACCEPTABLE for s in scores) / len(scores) if scores else 0.0,
            "scores": scores,
        }
        r = results[run.name]
        print(f"{run.name:22} {r['direction']}  judged {r['judged']}/{r['sampled']}  "
              f"mean {r['mean']:.1f}  acceptable {r['acceptable']:.0%}", flush=True)

    lines = [f"# Quality `{args.bench.name}`", "",
             f"MQM-lite, judged by DeepSeek v4.1 flash; acceptable = score >= {ACCEPTABLE}.", "",
             "| source | dir | judged | mean | acceptable |", "|---|---|---|---|---|"]
    for name, r in results.items():
        lines.append(f"| {name} | {r['direction']} | {r['judged']} | {r['mean']:.1f} | {r['acceptable']:.0%} |")
    for direction in sorted({r["direction"] for r in results.values()}):
        scores = [s for r in results.values() if r["direction"] == direction for s in r["scores"]]
        if scores:
            lines.append(
                f"| **{direction} overall** | | {len(scores)} | **{sum(scores) / len(scores):.1f}** | "
                f"**{sum(s >= ACCEPTABLE for s in scores) / len(scores):.0%}** |"
            )
    out = args.bench / "QUALITY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
