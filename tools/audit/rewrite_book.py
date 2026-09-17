"""Rewrite a book's output pages from their saved projects with the current writer, then merge.

A defect in the writer (not the translation) does not need the model again: every chunk's project
holds the translated document, so its page can be drawn again as it is. Used when a writer fix lands
after a book was translated - Figure 3.1 of Think Python, shifted by redaction, is fixed by
rewriting its page, not by translating it again.

    python tools/audit/rewrite_book.py --work _artifacts/campaign/runs/think_python --chunks failing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from translate_book import merge

from layoutkeep.core.docir import load_project
from layoutkeep.writers.pdf_writer import write_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--chunks", default="failing", help="'failing' (from audit.json), 'all', or a comma list")
    args = parser.parse_args()

    out_dir = args.work / "out"
    if args.chunks == "failing":
        chunks = json.loads((args.work / "audit.json").read_text(encoding="utf-8"))["failing_chunks"]
    elif args.chunks == "all":
        chunks = [p.stem.split("_")[1] for p in sorted(out_dir.glob("t_*.lkproj"))]
    else:
        chunks = [c.strip() for c in args.chunks.split(",") if c.strip()]

    for index in chunks:
        project = out_dir / f"t_{index}.lkproj"
        source = args.work / "src" / f"chunk_{index}.pdf"
        if project.exists() and source.exists():
            write_pdf(load_project(project), source, out_dir / f"t_{index}.pdf")
    print(f"rewrote {len(chunks)} page(s)")

    sources = sorted((args.work / "src").glob("chunk_*.pdf"))
    outputs = [out_dir / f"t_{p.stem.split('_')[1]}.pdf" for p in sources]
    if all(o.exists() for o in outputs):
        pages = merge(outputs, args.work / f"{args.work.name}.tr.pdf")
        print(f"merged {pages} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
