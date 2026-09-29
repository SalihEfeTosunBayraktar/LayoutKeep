"""Sweep every held-out run with the audit tools and write one table.

WHY THIS EXISTS: the audits are run per document while fixing something; nothing runs them over
*everything* and looks for the document that is out of line. A run with L7 = 11 or an unreadable
count that dwarfs the others is where the next bug is, and it is cheaper to find by sorting a
table than by reading thirty reports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def _run(script: str, target: Path) -> str:
    try:
        proc = subprocess.run(
            [PY, str(ROOT / "tools" / "audit" / script), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    return lines[-1] if lines else "?"


def _audit_counts(target: Path) -> dict[str, int]:
    """The L/D numbers for a run, from its own audit.json when it has one.

    The file holds a flat `counts` map (L1..L10, D1..D3 -> int) plus `lossless`, `blocks` and
    `chunks`; the first version of this helper guessed at a `found` structure that does not exist
    and crashed on the first run it met.
    """
    for candidate in (target / "audit.json", target / "out" / "audit.json"):
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            counts = data.get("counts")
            if isinstance(counts, dict):
                return {key: int(value) for key, value in counts.items() if isinstance(value, int)}
    return {}


def main() -> int:
    runs = []
    for base in (ROOT / "_artifacts/heldout/runs", ROOT / "_artifacts/heldout/live"):
        if base.exists():
            runs.extend(sorted(p for p in base.iterdir() if p.is_dir()))

    rows = []
    for run in runs:
        counts = _audit_counts(run)
        drift = _run("type_drift.py", run)
        over = _run("text_over_image.py", run)
        losses = {k: v for k, v in counts.items() if k.startswith("L") and v}
        row = {
            "run": run.name,
            "L": ", ".join(f"{k}={v}" for k, v in sorted(losses.items())) or "temiz",
            "drift": drift.split(":", 1)[-1].strip() if ":" in drift else drift,
            "over": over.split(":", 1)[-1].strip() if ":" in over else over,
        }
        rows.append(row)
        # Printed as it goes, not at the end: the first version collected everything and printed
        # once, so a run killed part-way left an empty file and no way to see how far it got.
        print(f"  {row['run']:34} {row['L']:28} {row['drift'][:44]}", flush=True)

    out = ROOT / "docs" / "AUDIT-SWEEP.md"
    lines = [
        "# Denetim taraması: tüm koşular, üç araç",
        "",
        "`tools/audit/sweep_runs.py` ile üretildi. Sıralama, en çok kayıp bildiren koşu üstte",
        "olacak şekilde: listenin başı bir sonraki hatanın arandığı yerdir.",
        "",
        "| Koşu | Kayıplar (audit.json) | type_drift | görsel üstü metin |",
        "|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: r["L"] == "temiz"):
        lines.append(f"| `{row['run']}` | {row['L']} | {row['drift']} | {row['over']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} koşu tarandı -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
