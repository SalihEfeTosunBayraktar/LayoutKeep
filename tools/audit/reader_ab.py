"""Read every held-out source with the original reader and with the working-tree one, and compare.

Writes one JSON per tree; run with PYTHONPATH pointing at the tree to measure.

Usage: python tools/audit/reader_ab.py <tree-src> <out.json>
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

from layoutkeep.readers.pdf_reader import read_pdf  # noqa: E402

root = Path("_artifacts/heldout/live")
shape: dict[str, list] = {}
for run in sorted(root.iterdir()):
    if not run.is_dir():
        continue
    for chunk in sorted((run / "src").glob("chunk_*.pdf")):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                doc = read_pdf(chunk)
            except Exception as error:  # noqa: BLE001 - a read that fails is a finding too
                shape[f"{run.name}/{chunk.stem}"] = [f"ERROR {type(error).__name__}: {error}"]
                continue
        rows = []
        for _page, block in doc.iter_blocks():
            for line in block.lines:
                rows.append([block.id, round(line.bbox.x0, 1), round(line.bbox.y0, 1), line.text])
        shape[f"{run.name}/{chunk.stem}"] = rows

Path(sys.argv[2]).write_text(json.dumps(shape, ensure_ascii=False, indent=0), encoding="utf-8")
print(f"{len(shape)} chunks written to {sys.argv[2]}")
