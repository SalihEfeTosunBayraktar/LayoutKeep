"""Find chunks whose saved project was read differently from how the current reader reads them.

A reader fix does not reach a book that was translated before it: `rewrite_book.py` redraws the
saved project, which still holds the old blocks. Think Python's Figure 11.1 kept its translated
labels ("dict" -> "sozluk") after the picture fix for exactly that reason, and a justified paragraph
cut in two by an older rule looked like one moved "." to the audit. Losses of that kind need not show
up in any count - a diagram's labels translated word for word lose nothing the audit can measure -
so every chunk is read again and compared with its project, and the ones that differ are the ones a
repair round has to translate again.

    python tools/audit/stale_chunks.py --work _artifacts/campaign/runs/think_python --json stale.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from layoutkeep.core.docir import load_project
from layoutkeep.ocr.layout_detector import load_detector
from layoutkeep.readers.pdf_reader import read_pdf

_MARKER = re.compile(r"</?\d+>")


def _reading(doc) -> list[tuple[str, str]]:
    """What a translation depends on: the text sent as each translatable block, page by page."""
    found = []
    for page in doc.pages:
        for block in page.blocks:
            if not block.translatable:
                continue
            source = _MARKER.sub("", block.source_text) if block.source_text else block.text
            found.append((page.source_ref, " ".join(source.split())))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    detector = load_detector()
    stale: dict[str, dict[str, int]] = {}
    chunks = sorted((args.work / "src").glob("chunk_*.pdf"))
    for chunk in chunks:
        index = chunk.stem.removeprefix("chunk_")
        project = args.work / "out" / f"t_{index}.lkproj"
        if not project.exists():
            continue
        saved = _reading(load_project(project))
        now = _reading(read_pdf(chunk, layout=detector))
        if saved != now:
            only_saved = len(set(saved) - set(now))
            only_now = len(set(now) - set(saved))
            stale[index] = {"blocks_before": len(saved), "blocks_now": len(now),
                            "only_before": only_saved, "only_now": only_now}
            print(f"stale {index}: {len(saved)} -> {len(now)} translatable blocks "
                  f"({only_saved} read differently before, {only_now} now)", flush=True)
    args.json.write_text(json.dumps({"checked": len(chunks), "stale": stale}, indent=2), encoding="utf-8")
    print(f"{len(stale)} of {len(chunks)} chunks read differently now", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
