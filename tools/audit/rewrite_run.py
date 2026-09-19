"""Re-write a recorded run's pages from its projects with the current writer, then audit them.

Reads only: the run directory is copied, so the recorded measurements stay as they were.

Usage: python tools/audit/rewrite_run.py <run-dir> [<dest-dir>]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "src")

from layoutkeep.core.docir import load_project  # noqa: E402
from layoutkeep.writers.pdf_writer import write_pdf  # noqa: E402


def main() -> int:
    run = Path(sys.argv[1])
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else run.with_name(run.name + "_rewritten")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run, dest)
    for out_pdf in sorted((dest / "out").glob("t_*.pdf")):
        project = out_pdf.with_suffix(".lkproj")
        number = project.stem.removeprefix("t_")
        source = dest / "src" / f"chunk_{number}.pdf"
        if not source.exists():
            source = dest / "src" / f"{number}.pdf"
        if not source.exists():
            print(f"!! no source for {out_pdf.name}: look for chunk_{number}.pdf in {dest / 'src'}")
            continue
        write_pdf(load_project(project), source, out_pdf)
        print(f"rewrote {out_pdf.name} from {project.name} (source {source.name})")
    return subprocess.call(
        [sys.executable, "tools/audit/lossless_audit.py", "--work", str(dest), "--to", "tr"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
