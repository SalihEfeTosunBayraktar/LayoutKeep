"""Re-translate the chunks the lossless audit found losses in, then audit again.

A failure the pipeline cannot prevent - a batch reply that came back without one segment while
the server was under load, a model that echoed a paragraph once - does not repeat when the chunk
is translated again. So a book is verified, and what failed is redone with the current code, up to
a few rounds; every round is recorded, so a loss that keeps coming back is visible as exactly that.

    python tools/audit/repair_book.py --work _artifacts/campaign/runs/nist --source book.pdf --rounds 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PY = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()

    name = args.work.name
    history = []
    for round_no in range(1, args.rounds + 1):
        audit = json.loads((args.work / "audit.json").read_text(encoding="utf-8"))
        failing = audit.get("failing_chunks", [])
        history.append({"round": round_no, "failing_before": failing, "counts": audit["counts"]})
        print(f"[repair {name}] round {round_no}: {len(failing)} chunk(s) with losses {failing}", flush=True)
        if not failing:
            break
        for index in failing:
            for suffix in (".pdf", ".lkproj", ".log"):
                (args.work / "out" / f"t_{index}{suffix}").unlink(missing_ok=True)
        subprocess.run(
            [PY, "tools/audit/translate_book.py", str(args.source), "--out", str(args.work / f"{name}.tr.pdf"),
             "--work", str(args.work), "--model", "google/gemma-4-e4b", "--workers", "8",
             "--pages-per-chunk", "1", "--layout-detector", "--resume"],
            check=False,
        )
        with (args.work / "audit.txt").open("w", encoding="utf-8") as out:
            subprocess.run(
                [PY, "tools/audit/lossless_audit.py", "--work", str(args.work), "--json", str(args.work / "audit.json")],
                stdout=out, stderr=subprocess.STDOUT, check=False,
            )
    final = json.loads((args.work / "audit.json").read_text(encoding="utf-8"))
    history.append({"final": True, "failing": final.get("failing_chunks", []), "counts": final["counts"]})
    (args.work / "repair_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(f"[repair {name}] final counts {final['counts']} lossless={final['lossless']}", flush=True)
    return 0 if final["lossless"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
