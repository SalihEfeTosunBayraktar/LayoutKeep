"""Compare the point sizes inside each box, source against written page.

WHY THIS EXISTS: `type_drift.py` divides every written line whose centre falls inside a block's
recorded box by that box's *single* recorded style. A 6 pt footnote marker inside an 11 pt block
therefore reads as a 0.55x "shrink" and text from a neighbouring block that strayed into the box
reads as anything at all - which is why one run reported 0.26x "squeezed" blocks in a pipeline
whose fitting floor is `MIN_SCALE = 0.85` and where such a draw is impossible. The ratio was
measuring boxes against the runs inside them.

This instrument answers the question that one was meant to answer, without the confound: for each
box it collects the *set of point sizes the source prints there* and the set the written page prints
there, and names the difference.

    faithful    the written sizes match the source's, whatever they are
    flattened   the source had a small run (marker, formula fragment, footnote) and the written
                page prints everything at the box's larger size
    shrunk      the whole box came out smaller than the source (the fitting ladder)
    grown       the whole box came out larger
    mixed       some runs held their size and others moved

It pairs `out/t_NNNN.pdf` with `src/chunk_NNNN.pdf` (the convention the campaign writes) and matches
boxes by overlap, so it needs no model and can run while a translation owns the GPU.

Usage:  python tools/audit/type_map.py <run dir> [--verbose]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf

SIZE_TOLERANCE = 0.35  # pt: the same face through two extractors reports small differences


def _sizes_by_box(page: pymupdf.Page, min_chars: int = 4) -> list[tuple[tuple[float, float, float, float], set[float], str]]:
    """Every text block on the page: its box, the point sizes it prints, and its text."""
    out: list[tuple[tuple[float, float, float, float], set[float], str]] = []
    for raw in page.get_text("dict").get("blocks", []):
        if raw.get("type") != 0:
            continue
        sizes: set[float] = set()
        text_parts: list[str] = []
        for line in raw.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    sizes.add(round(span["size"], 1))
                    text_parts.append(span["text"])
        text = " ".join("".join(text_parts).split())
        if len(text) >= min_chars and sizes:
            out.append((tuple(raw["bbox"]), sizes, text))
    return out


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _verdict(src: set[float], out: set[float]) -> str:
    if not src or not out:
        return "?"
    s_big, s_small = max(src), min(src)
    o_big, o_small = max(out), min(out)
    if abs(s_big - o_big) <= SIZE_TOLERANCE and abs(s_small - o_small) <= SIZE_TOLERANCE:
        return "faithful"
    if abs(s_big - o_big) <= SIZE_TOLERANCE and o_small > s_small + SIZE_TOLERANCE:
        return "flattened"
    if o_big < s_big - SIZE_TOLERANCE:
        return "shrunk"
    if o_big > s_big + SIZE_TOLERANCE:
        return "grown"
    return "mixed"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    src_dir, out_dir = args.run / "src", args.run / "out"
    if not src_dir.is_dir() or not out_dir.is_dir():
        print(f"{args.run}: src/ and out/ are both required")
        return 1

    counts: dict[str, int] = {}
    rows: list[tuple[str, str, str, set[float], set[float], str]] = []
    for src_path in sorted(src_dir.glob("*.pdf")):
        index = "".join(ch for ch in src_path.stem if ch.isdigit())
        pairs = sorted(out_dir.glob(f"t_{index}.pdf")) if index else []
        if not pairs:
            continue
        with pymupdf.open(src_path) as sdoc, pymupdf.open(pairs[0]) as odoc:
            spage = sdoc[0]
            opage = odoc[0]
            written = _sizes_by_box(opage)
            for box, sizes, text in _sizes_by_box(spage):
                best, score = None, 0.0
                for wbox, wsizes, _wtext in written:
                    area = _overlap(box, wbox)
                    if area > score:
                        best, score = wsizes, area
                if best is None:
                    continue
                verdict = _verdict(sizes, best)
                counts[verdict] = counts.get(verdict, 0) + 1
                rows.append((pairs[0].name, verdict, text[:54], sizes, best, verdict))

    name = args.run.name
    total = sum(counts.values())
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(f"{name}: {total} boxes - {summary}")
    if args.verbose:
        for label in ("flattened", "grown", "mixed", "shrunk"):
            picked = [r for r in rows if r[1] == label]
            if not picked:
                continue
            print(f"--- {label} ({len(picked)})")
            for fname, _v, text, sizes, best, _x in picked[:10]:
                print(f"    {fname}: kaynak={sorted(sizes)} çıktı={sorted(best)}  {text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
