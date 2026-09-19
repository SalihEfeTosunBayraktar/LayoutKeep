"""How far does the written page's type drift from what the pipeline decided?

WHY THIS EXISTS: the user reported headings and numbers losing their alignment and some blocks
coming out in an obviously larger face. The first measurement of this was wrong - it matched the
written line against the *nearest* source line by height, and on a form every label shares its
height band with its value, so a 10pt label was "compared" with a 12pt neighbour and a correct page
looked inflated. This compares each block against the style the reader recorded for that block,
matched by geometry, and reports:

  * blocks drawn larger than their source style (a headline that grew),
  * blocks drawn smaller (the fitting ladder, expected on long translations),
  * blocks whose alignment no longer matches what the reader inferred.

Usage:  python tools/audit/type_drift.py <run dir> [--verbose]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from layoutkeep.core.docir import Block, load_project  # noqa: E402

#: A block drawn this much larger than its own style stands out against the page.
INFLATED = 1.20
#: ...and this much smaller is the fitting ladder doing its job; counted, not alarmed about.
SHRUNK = 0.80

#: Below this, a line is not read by anyone: the D1 readability floor.
FLOOR_PT = 5.0


def _written_lines(page: pymupdf.Page, block: Block) -> list[tuple[float, pymupdf.Rect]]:
    """Written lines whose centre sits inside the block's box, with their drawn size."""
    box = pymupdf.Rect(block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
    found: list[tuple[float, pymupdf.Rect]] = []
    for raw in page.get_text("dict").get("blocks", []):
        if raw.get("type") != 0:
            continue
        for line in raw.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            rect = pymupdf.Rect(line["bbox"])
            centre = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            if box.contains(centre):
                found.append((statistics.median(span["size"] for span in spans), rect))
    return found


def _alignment_of(lines: list[pymupdf.Rect]) -> str:
    """What the drawn lines look like: left, right, centre or mixed."""
    if len(lines) < 2:
        return "left"
    lefts = [rect.x0 for rect in lines]
    rights = [rect.x1 for rect in lines]
    if max(rights) - min(rights) <= 2.0 and max(lefts) - min(lefts) > 6.0:
        return "right"
    if max(lefts) - min(lefts) <= 2.0 and max(rights) - min(rights) > 6.0:
        return "left"
    return "mixed"


def drift(source: Path, output: Path, project: Path) -> dict[str, list[tuple]]:
    """Compare one written page against the styles the pipeline recorded for it."""
    document = load_project(project)
    page_data = document.pages[0]
    result: dict[str, list[tuple]] = {"inflated": [], "shrunk": [], "alignment": [], "floor": []}
    with pymupdf.open(output) as written_doc:
        page = written_doc[0]
        for block in page_data.blocks:
            if not block.text.strip() or abs(block.rotation) > 0.1:
                continue
            style = block.dominant_style()
            if style.size <= 0:
                continue
            lines = _written_lines(page, block)
            if not lines:
                continue
            drawn = statistics.median(size for size, _ in lines)
            ratio = drawn / style.size
            row = (round(ratio, 2), round(style.size, 1), round(drawn, 1), block.text[:38])
            if ratio >= INFLATED:
                result["inflated"].append(row)
            elif ratio <= SHRUNK:
                result["shrunk"].append(row)
            if drawn < FLOOR_PT:
                result["floor"].append(row)
            drawn_alignment = _alignment_of([rect for _, rect in lines])
            if block.align in ("left", "right", "center") and drawn_alignment not in (block.align, "mixed"):
                result["alignment"].append((block.align, drawn_alignment, block.text[:38]))
    return result


def scan(run: Path, verbose: bool = False) -> dict[str, int]:
    """Report the drift across every chunk of a recorded run."""
    totals = {"inflated": 0, "shrunk": 0, "alignment": 0, "floor": 0, "blocks": 0}
    worst: list[tuple[float, str, str, str]] = []
    for source in sorted((run / "src").glob("chunk_*.pdf")):
        output = run / "out" / source.name.replace("chunk_", "t_")
        project = run / "out" / output.name.replace(".pdf", ".lkproj")  # t_000N.lkproj, not chunk_
        if not (output.exists() and project.exists()):
            continue
        found = drift(source, output, project)
        for key, rows in found.items():
            totals[key] += len(rows)
            for row in rows:
                worst.append((row[0], key, output.name, str(row[-1])))
    print(f"{run.name}: {totals['inflated']} büyümüş, {totals['shrunk']} küçülmüş, "
          f"{totals['alignment']} hizası değişmiş, {totals['floor']} okunamaz boyutta")
    if verbose:
        for key in ("inflated", "floor", "alignment"):
            print(f"--- {key} ---")
            for row in sorted([item for item in worst if item[1] == key], reverse=True)[:8]:
                print(f"    {row[2]}: {row[0]}  '{row[3]}'")
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    totals = scan(args.run, args.verbose)
    # Exit status says whether anything needs looking at, so a sweep can be scripted.
    return 0 if not (totals["inflated"] or totals["alignment"] or totals["floor"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
