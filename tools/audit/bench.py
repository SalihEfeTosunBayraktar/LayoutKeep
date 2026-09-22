"""One command that measures the committed code on a fixed set of sources, and one table per commit.

WHY THIS EXISTS: forty held-out runs sit under `_artifacts/heldout/live`, but each was taken with a
different commit (`_r2`, `_r3` ...), so "how lossless is the product today?" had no single answer and
a fix could not be told apart from a drift. The bench translates the same three pages of every source
with HEAD, audits them with the same criteria (`lossless_audit.py`), and writes the table under the
commit's short hash, so two commits compare line by line.

Three rules keep the number honest:
- the translation memory is off (`--memory none`), or a re-run would read yesterday's translations
  back from the cache and measure nothing of today's code;
- the working tree must be clean, so the hash in the table is the code that ran;
- the model server is kept full: every page is its own chunk and several sources run at once, so
  about `--parallel` x 3 chunks are in flight (the first version ran one three-page chunk per source,
  one source after the other, and left six of the server's eight slots idle).

    python tools/audit/bench.py                      # the whole suite, ~1-2 h with a local model
    python tools/audit/bench.py --only arxiv_19145   # one source
    python tools/audit/bench.py --table              # rebuild the table from finished runs
    python tools/audit/bench.py --label glossary --set translation.auto_glossary=true   # an arm

Settings are pinned per arm: the run reads `<bench dir>/tunables.json` (the user's own overrides plus
every `--set`) through LAYOUTKEEP_TUNABLES, never the live settings file the application edits.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
SOURCES = ROOT / "_artifacts" / "heldout" / "sources"
BENCH = ROOT / "_artifacts" / "bench"

#: name, source file, source language, target language. Chosen so every reader path and failure class
#: the held-out campaign found is in the set: academic papers with references, a wiki article, tax
#: forms with numbers, a text-less scan, 19th-century scans, a science journal, and the reverse
#: direction on Turkish law and planning documents.
SUITE: list[tuple[str, str, str, str]] = [
    ("arxiv_19145", "arxiv_2609.19145.pdf", "en", "tr"),
    ("arxiv_19113", "arxiv_2609.19113.pdf", "en", "tr"),
    ("arxiv_18014", "arxiv_2605.18014v1.pdf", "en", "tr"),
    ("plos", "plos_pone_0235750.pdf", "en", "tr"),
    ("wiki_photosynthesis", "wikipedia_photosynthesis.pdf", "en", "tr"),
    ("wiki_printing_press", "wikipedia_printing_press.pdf", "en", "tr"),
    ("irs_p505", "irs_p505.pdf", "en", "tr"),
    ("irs_i1040gi", "irs_i1040gi.pdf", "en", "tr"),
    ("nist_jres", "nist_jres_v98n1.pdf", "en", "tr"),
    ("nist_vapor_scan", "nist_ir6643_vapor_pressure.pdf", "en", "tr"),
    ("nasa_scan", "nasa_ntrs_19750007530.pdf", "en", "tr"),
    ("cookbook_1907", "archive_cookbook_1907.pdf", "en", "tr"),
    ("mushrooms_1895", "archive_mushrooms_1895_every3rd.pdf", "en", "tr"),
    ("history_of_math", "gutenberg_31061_history_of_mathematics.pdf", "en", "tr"),
    ("sbb_plan_12_en", "sbb_development_plan_12_en.pdf", "en", "tr"),
    ("tr_tck_5237", "tr/tck_5237.pdf", "tr", "en"),
    ("tr_kalkinma_12", "tr/kalkinma_plani_12.pdf", "tr", "en"),
    # Two sources said nothing about the reverse direction: 72 blocks against 1051 the other way.
    ("tr_kalkinma_11", "tr/kalkinma_plani_11.pdf", "tr", "en"),
    ("tr_cmk_5271", "tr/cmk_5271.pdf", "tr", "en"),
    ("tr_tmk_4721", "tr/tmk_4721.pdf", "tr", "en"),
    ("tr_shk_2828", "tr/shk_2828.pdf", "tr", "en"),
]

LOSS_KEYS = [f"L{n}" for n in range(1, 11)]
#: Block-level criteria that say the page's shape did not survive: text missing from the page, drawn off
#: it, drawn on a figure, or shrunk below the readability floor. L7 and L8 count pages, not blocks, so
#: they are not in the ratio - they must be zero on their own.
LAYOUT_BLOCK_KEYS = ["L3", "L4", "L10", "D1"]
DIAG_KEYS = ["D1", "D2", "D3"]


def _git(*args: str) -> str:
    # git from PATH on purpose: the bench runs on the developer's machine, where git is the one on PATH.
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True  # noqa: S607
    ).stdout.strip()


def _pages(count: int) -> list[int]:
    """First, middle and last-but-one: the front matter, the body, and where references live."""
    return sorted({0, count // 2, max(0, count - 2)})


def _cut(source: Path, target: Path) -> int:
    import pymupdf

    doc = pymupdf.open(source)
    doc.select(_pages(doc.page_count))
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(target)
    return doc.page_count


def _run_one(name: str, file: str, src_lang: str, dst_lang: str, run_dir: Path, args) -> dict:
    work = run_dir / name
    source = work / "source.pdf"
    pages = _cut(SOURCES / file, source)
    started = time.time()
    translate = subprocess.run(
        [PY, str(ROOT / "tools/audit/translate_book.py"), str(source),
         "--out", str(work / f"{name}.{dst_lang}.pdf"), "--work", str(work / "run"),
         "--from", src_lang, "--to", dst_lang, "--model", args.model, "--workers", str(pages),
         "--pages-per-chunk", "1", "--layout-detector", "--memory", "none", "--force"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=args.env,
    )
    (work / "translate.log").write_text(translate.stdout + translate.stderr, encoding="utf-8")
    seconds = round(time.time() - started)
    audit = subprocess.run(
        [PY, str(ROOT / "tools/audit/lossless_audit.py"), "--work", str(work / "run"),
         "--json", str(work / "audit.json"), "--to", dst_lang],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    (work / "audit.txt").write_text(audit.stdout + audit.stderr, encoding="utf-8")
    result = {"name": name, "pages": pages, "seconds": seconds, "direction": f"{src_lang}->{dst_lang}",
              "translate_exit": translate.returncode}
    (work / "bench.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _row(work: Path) -> dict | None:
    meta_file, audit_file = work / "bench.json", work / "audit.json"
    if not meta_file.exists():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    counts = {}
    if audit_file.exists():
        counts = json.loads(audit_file.read_text(encoding="utf-8")).get("counts") or {}
    meta["counts"] = counts
    meta["blocks"] = 0
    if audit_file.exists():
        meta["blocks"] = int(json.loads(audit_file.read_text(encoding="utf-8")).get("blocks") or 0)
    return meta


def layout_ratio(row: dict) -> float | None:
    """Share of the translated blocks drawn with the page's shape intact (the user's third bar)."""
    if not row.get("blocks"):
        return None
    bad = sum(int(row["counts"].get(key, 0)) for key in LAYOUT_BLOCK_KEYS)
    return max(0.0, 1 - bad / row["blocks"])


def write_table(run_dir: Path) -> Path:
    rows = [row for work in sorted(run_dir.iterdir()) if work.is_dir() and (row := _row(work))]
    header = ["source", "dir", "pages", "s", *LOSS_KEYS, "losses", *DIAG_KEYS, "layout"]
    lines = [
        f"# Bench `{run_dir.name}`",
        "",
        (
            f"Commit `{run_dir.name}`, translation memory off, three pages per source "
            "(first, middle, last-but-one). L = loss criteria, D = reported only."
        ),
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    total = dict.fromkeys(LOSS_KEYS + DIAG_KEYS, 0)
    for row in rows:
        counts = row["counts"]
        if not counts:
            cells = [row["name"], row["direction"], str(row["pages"]), str(row["seconds"]),
                     *(["-"] * len(LOSS_KEYS)), f"no audit (exit {row['translate_exit']})",
                     *(["-"] * len(DIAG_KEYS)), "-"]
        else:
            losses = sum(int(counts.get(key, 0)) for key in LOSS_KEYS)
            for key in total:
                total[key] += int(counts.get(key, 0))
            cells = [row["name"], row["direction"], str(row["pages"]), str(row["seconds"]),
                     *(str(counts.get(key, 0)) for key in LOSS_KEYS), f"**{losses}**",
                     *(str(counts.get(key, 0)) for key in DIAG_KEYS),
                     f"{layout_ratio(row):.0%}" if layout_ratio(row) is not None else "-"]
        lines.append("| " + " | ".join(cells) + " |")
    lossless = sum(1 for row in rows if row["counts"]
                   and not sum(int(row["counts"].get(k, 0)) for k in LOSS_KEYS))
    lines.append("| **total** | | | | " + " | ".join(str(total[k]) for k in LOSS_KEYS)
                 + f" | **{sum(total[k] for k in LOSS_KEYS)}** | "
                 + " | ".join(str(total[k]) for k in DIAG_KEYS) + " | |")
    for direction in sorted({row["direction"] for row in rows}):
        group = [row for row in rows if row["direction"] == direction and row.get("blocks")]
        blocks = sum(row["blocks"] for row in group)
        bad = sum(int(row["counts"].get(k, 0)) for row in group for k in LAYOUT_BLOCK_KEYS)
        pages = sum(int(row["counts"].get(k, 0)) for row in group for k in ("L7", "L8"))
        if blocks:
            lines.append(f"| **{direction} layout** | | | | {max(0.0, 1 - bad / blocks):.1%} of {blocks} "
                         f"blocks intact, L7+L8 pages {pages} |" + " |" * (len(header) - 5))
    lines += ["", f"Lossless sources: **{lossless} / {len(rows)}**", ""]
    table = run_dir / "BENCH.md"
    table.write_text("\n".join(lines), encoding="utf-8")
    return table


def _pin_settings(run_dir: Path, pairs: list[str]) -> dict:
    """Write this arm's settings file and return the environment that points the runs at it."""
    import os

    from layoutkeep.core import tunables

    settings = {}
    live = tunables.storage_path()
    if live.exists():
        settings = json.loads(live.read_text(encoding="utf-8"))
    for pair in pairs:
        key, _, value = pair.partition("=")
        spec = tunables.definition(key)  # a typo fails here, before an hour of translating
        settings[key] = value.lower() in ("1", "true", "yes") if spec.kind == "bool" else value
    pinned = run_dir / "tunables.json"
    pinned.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    return {**os.environ, "LAYOUTKEEP_TUNABLES": str(pinned)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", default=None, help="run only these source names")
    parser.add_argument("--model", default="google/gemma-4-e4b")
    parser.add_argument("--parallel", type=int, default=3, help="sources translated at the same time")
    parser.add_argument("--table", action="store_true", help="only rebuild the table of HEAD's run")
    parser.add_argument("--label", default="", help="arm name, appended to the bench directory")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="pin a setting for this arm (repeatable)")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="measure an uncommitted tree (the table is then marked -dirty)")
    args = parser.parse_args()

    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    if dirty and not (args.allow_dirty or args.table):
        print("the working tree has uncommitted changes; commit first or pass --allow-dirty")
        return 2
    name = _git("rev-parse", "--short", "HEAD") + ("-dirty" if dirty else "")
    run_dir = BENCH / (f"{name}-{args.label}" if args.label else name)
    run_dir.mkdir(parents=True, exist_ok=True)
    args.env = _pin_settings(run_dir, args.set)

    if not args.table:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        wanted = [item for item in SUITE if args.only is None or item[0] in args.only]
        print(f"[{time.strftime('%H:%M:%S')}] {len(wanted)} sources, {args.parallel} at a time", flush=True)
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(_run_one, *item, run_dir, args): item[0] for item in wanted}
            for done, future in enumerate(as_completed(futures), 1):
                name = futures[future]
                result = future.result()
                row = _row(run_dir / name)
                losses = {k: v for k, v in (row["counts"] if row else {}).items() if k.startswith("L") and v}
                print(f"[{time.strftime('%H:%M:%S')}] {done}/{len(wanted)} {name}  {result['seconds']} s  "
                      f"exit {result['translate_exit']}  {losses or 'lossless'}", flush=True)
                write_table(run_dir)
    print(write_table(run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
