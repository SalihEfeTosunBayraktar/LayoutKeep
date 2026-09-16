"""What the layout model does on its own, before anything is built on top of it.

Each detected region is taken as a block exactly as the model drew it: no XY-cut, no paragraph
rules, no size ceiling, no reordering. OCR lines are used only to see what falls in each region.
The point is to know how much of the problem the model solves by itself, so whatever is added
afterwards is added against a measured baseline instead of a guess.

Per page it reports:

  regions     how many the model returned above the threshold
  dup         prose regions lying mostly inside another prose region - the same text boxed
              twice. A field inside a form or a label inside a picture is hierarchy, not this.
  orphan      OCR lines in no region - text the model missed
  shared      OCR lines inside two or more regions that do not nest - ambiguous ownership
  frag        regions whose text starts in lowercase (a paragraph cut in half)
  mixed_col   regions holding lines from two x-clusters more than a line height apart - a
              margin note or a second column boxed with the body
  labels      count per label

and writes `<work>/pure_<name>.png` with the regions drawn, for looking at, because the numbers
cannot say whether a box is right.

    python tools/audit/layout_pure.py --source book.pdf --pages 22,28 --dpi 200
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from layoutkeep.ocr.engine import RapidOcrEngine
from layoutkeep.ocr.layout_detector import load_detector
from layoutkeep.readers.image_reader import _merge_boxes_into_lines

_COLORS = {"text": "red", "section_header": "blue", "title": "blue", "caption": "green",
           "picture": "orange", "table": "orange", "formula": "purple", "list_item": "brown",
           "page_header": "gray", "page_footer": "gray", "footnote": "teal"}


def _say(line: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


def _inside(inner, outer, share: float = 0.5) -> bool:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = max((inner[2] - inner[0]) * (inner[3] - inner[1]), 1e-6)
    return ix * iy / area >= share


def measure(image: Image.Image, detector, engine, out_png: Path) -> dict:
    regions = detector.detect(image)
    lines = _merge_boxes_into_lines(engine.recognize(image))
    line_boxes = [
        (min(b.bbox[0] for b in ln), min(b.bbox[1] for b in ln),
         max(b.bbox[2] for b in ln), max(b.bbox[3] for b in ln)) for ln in lines
    ]
    line_text = [" ".join(b.text for b in ln) for ln in lines]
    line_h = statistics.median(b[3] - b[1] for b in line_boxes) if line_boxes else 1.0

    containers = {"picture", "table", "form", "key_value_region"}
    nested = sum(
        1 for i, r in enumerate(regions)
        if r.label not in containers and any(
            i != j and o.label not in containers and _inside(r.bbox, o.bbox, 0.8)
            for j, o in enumerate(regions)
        )
    )
    # A region with another region inside it is judged through its children, not as a block.
    parents = {
        j for i, r in enumerate(regions) for j, o in enumerate(regions)
        if i != j and _inside(r.bbox, o.bbox, 0.8)
    }
    orphan = shared = 0
    members: dict[int, list[int]] = {}
    for li, lb in enumerate(line_boxes):
        holders = [ri for ri, r in enumerate(regions) if _inside(lb, r.bbox)]
        if not holders:
            orphan += 1
            continue
        independent = [
            a for a in holders
            if not any(a != b and (_inside(regions[a].bbox, regions[b].bbox, 0.8)
                                   or _inside(regions[b].bbox, regions[a].bbox, 0.8))
                       for b in holders)
        ]
        if len(independent) > 1:
            shared += 1
        for ri in holders:
            members.setdefault(ri, []).append(li)

    frag = mixed = 0
    for ri, lis in members.items():
        if regions[ri].label in containers or ri in parents:
            continue
        lis.sort(key=lambda i: (line_boxes[i][1], line_boxes[i][0]))
        text = " ".join(line_text[i] for i in lis).strip()
        if text[:1].islower() and len(text) > 30:
            frag += 1
        lefts = sorted(line_boxes[i][0] for i in lis)
        if any(b - a > line_h * 3 for a, b in pairwise(lefts)):
            mixed += 1

    draw_img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(draw_img)
    for r in regions:
        color = _COLORS.get(r.label, "black")
        draw.rectangle(r.bbox, outline=color, width=3)
        draw.text((r.bbox[0] + 2, r.bbox[1] - 11), f"{r.label} {r.score:.2f}", fill=color)
    draw_img.save(out_png)

    return {
        "regions": len(regions), "dup": nested, "orphan": orphan, "lines": len(lines),
        "shared": shared, "frag": frag, "mixed_col": mixed,
        "labels": dict(Counter(r.label for r in regions)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--pages", default="1", help="1-based, applied to every source")
    parser.add_argument("--dpi", type=float, default=200.0)
    parser.add_argument("--work", type=Path, default=Path("_artifacts/pure"))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    detector = load_detector()
    if detector is None:
        _say("layout model not installed")
        return 1
    engine = RapidOcrEngine()

    totals: Counter = Counter()
    _say(f"{'page':<34} {'reg':>3} {'dup':>4} {'orph':>4}/{'lines':<5} {'shar':>4} {'frag':>4} {'mixc':>4}  labels")
    for source in args.source:
        with pymupdf.open(str(source)) as doc:
            pages = [int(p) for p in args.pages.split(",")] if args.pages != "all" else range(1, doc.page_count + 1)
            for number in pages:
                if number > doc.page_count:
                    continue
                pix = doc[number - 1].get_pixmap(dpi=int(args.dpi))
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                name = f"{source.stem[:24]}_p{number}"
                m = measure(image, detector, engine, args.work / f"pure_{name}.png")
                for key in ("regions", "dup", "orphan", "lines", "shared", "frag", "mixed_col"):
                    totals[key] += m[key]
                _say(f"{name:<34} {m['regions']:3d} {m['dup']:4d} {m['orphan']:4d}/{m['lines']:<5d} "
                     f"{m['shared']:4d} {m['frag']:4d} {m['mixed_col']:4d}  {m['labels']}")
    _say("")
    _say("TOTAL " + "  ".join(f"{k} {totals[k]}" for k in
                             ("regions", "dup", "orphan", "lines", "shared", "frag", "mixed_col")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
