"""Run one source through the real pipeline and audit it, against a recorded run where there is one.

The campaign's held-out runs are `.sh` scripts that pin a commit and a directory layout; this is the
same measurement for a single source, with the code on disk right now, and it prints the comparison
to the run recorded before the change under test.

    python tools/audit/live_check.py _artifacts/heldout/sources/nasa_ntrs_19750007530.pdf \
        --name nasa_ntrs_scan --chunks 1 --workers 7

Exit code 0 when the audit is lossless, 1 when it is not, 2 when the source is missing, so a loop
or CI can tell without reading the output.

Output goes to `_artifacts/heldout/live/<name>` (never into `_artifacts/heldout/runs/<name>`, which
holds the recorded measurement), and the audit is compared against that recorded run automatically.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.core import tunables  # noqa: E402

LABELS = [
    ("L1", "same pages"), ("L2", "left untranslated"), ("L3", "text not on the page"),
    ("L4", "off the page"), ("L5", "markup leaked"), ("L6", "numbers lost"),
    ("L7", "text over text"), ("L8", "untouched moved"), ("L9", "garbled letters"),
    ("D1", "below readability"), ("D2", "short, unchanged"), ("D3", "squeezed lines"),
]


def _say(line: str = "") -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


def _command(source: Path, work: Path, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable, str(ROOT / "tools/audit/translate_book.py"), str(source),
        "--out", str(work / f"{args.name}.tr.pdf"), "--work", str(work),
        "--model", args.model, "--base-url", args.base_url,
        "--workers", str(args.workers), "--pages-per-chunk", str(args.pages_per_chunk),
    ]
    if args.chunks:
        command += ["--limit-chunks", str(args.chunks)]
    if args.resume:
        command += ["--resume"]
    if args.preserve_references:
        command += ["--preserve-references"]
    if args.fit_mode:
        command += ["--fit-mode", args.fit_mode]
    return command


def translate(source: Path, work: Path, args: argparse.Namespace) -> Path:
    out = work / f"{args.name}.tr.pdf"
    started = time.time()
    _say(f"translating {source.name} with {args.model}, {args.workers} workers")
    proc = subprocess.run(
        _command(source, work, args), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    (work / "translate.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    _say(f"  exit {proc.returncode} in {time.time() - started:.0f}s - log {work / 'translate.log'}")
    if not out.exists():
        _say("  NO OUTPUT WRITTEN")
    return out


def audit(work: Path, args: argparse.Namespace) -> dict:
    payload = work / "audit.json"
    subprocess.run(
        [
            sys.executable, str(ROOT / "tools/audit/lossless_audit.py"),
            "--work", str(work), "--json", str(payload), "--to", args.to,
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return json.loads(payload.read_text(encoding="utf-8")) if payload.exists() else {}


def show(result: dict, recorded: Path | None) -> None:
    counts = result.get("counts", {})
    _say(
        f"chunks {result.get('chunks')}  blocks {result.get('blocks')}  "
        f"LOSSLESS {result.get('lossless')}"
    )
    before = (
        json.loads(recorded.read_text(encoding="utf-8")).get("counts", {})
        if recorded and recorded.exists()
        else {}
    )
    for key, label in LABELS:
        change = f"   (was {before[key]}, {counts.get(key, 0) - before[key]:+d})" if key in before else ""
        _say(f"  {key}  {label:<20} {counts.get(key, 0):5d}{change}")
    for key in ("L2", "L3", "L6", "L7", "L8"):
        for example in (result.get("examples", {}).get(key) or [])[:3]:
            _say(f"      {key}: {example[:110]}")


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--name", required=True, help="name of the run directory and its outputs")
    parser.add_argument("--work", type=Path, default=None)
    parser.add_argument("--model", default="google/gemma-4-e4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--workers", type=int, default=int(tunables.get("translation.workers")))
    parser.add_argument("--pages-per-chunk", type=int, default=1)
    parser.add_argument("--chunks", type=int, default=0, help="stop after N chunks (a smoke run)")
    parser.add_argument("--to", default="tr")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preserve-references", action="store_true", dest="preserve_references")
    parser.add_argument(
        "--fit-mode", default=None, choices=["strict", "reflow"],
        help="forward the fitting mode; omit for the application's default",
    )
    parser.add_argument("--against", type=Path, default=None, help="a recorded audit.json to compare")
    args = parser.parse_args()

    work = args.work or (ROOT / "_artifacts/heldout/live" / args.name)
    work.mkdir(parents=True, exist_ok=True)
    source = args.source if args.source.is_absolute() else (ROOT / args.source)
    if not source.exists():
        _say(f"source not found: {source}")
        return 2

    translate(source, work, args)
    result = audit(work, args)
    # The recorded run of the same source, if the campaign measured one: the comparison is against
    # a first-class measurement, never against this run's own earlier output.
    recorded = args.against or (ROOT / "_artifacts/heldout/runs" / args.name / "audit.json")
    show(result, recorded if recorded.exists() else None)
    return 0 if result.get("lossless") else 1


if __name__ == "__main__":
    raise SystemExit(main())
