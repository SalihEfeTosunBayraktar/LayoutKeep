"""Measure reader output over a SAMPLE of pages, not one, so a fix cannot hide a regression.

Every constant in the scanned-page path was calibrated on a single page, and every one of them
later broke a different page. 200 DPI was chosen on page 61 and mangled page 54. The line-join
ratio was measured on page 61's figure labels. The indent tolerance was measured on page 22.
Each time the fix was verified on the page that motivated it, which is exactly how the next page
got broken.

This runs the reader over a spread of pages and reports the properties a good read has, per page
and in aggregate, so "better" has to mean better across the sample:

  blocks            how many the reader found
  frag              blocks beginning mid-sentence - a paragraph cut in half
  size_spread       p90/median font size on the page; a page of body text should be near 1.0,
                    and a large number means something was taken for a heading
  tall              single-line blocks whose box is over 1.6x the page median line height
  lowconf           blocks under the review threshold
  chars             recovered characters

No thresholds are asserted here on purpose. This is an instrument, not a gate: the numbers are
for comparing a change against the run before it.

    python tools/audit/page_eval.py --pages 22,28,54,61,101,121,251,301,401,451
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import pymupdf

from layoutkeep.readers.pdf_reader import read_pdf

#: A spread chosen to cover what has actually bitten: margin notes and indented prose (22),
#: Karnaugh grids (28), an exercise list where 200 DPI failed (54), tables and figures (61),
#: a low-resolution page (101), register-transfer tables (121), plain prose (251, 301, 401),
#: and a second page that failed at 200 DPI (451).
DEFAULT_PAGES = (22, 28, 54, 61, 101, 121, 251, 301, 401, 451)


def _say(line: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


def measure_page(path: Path, classifier=None) -> dict[str, float]:
    page = read_pdf(path, classifier=classifier).pages[0]
    blocks = page.blocks
    if not blocks:
        return {"blocks": 0, "frag": 0, "size_spread": 0.0, "tall": 0, "lowconf": 0, "chars": 0}

    sizes = sorted(b.dominant_style().size for b in blocks)
    median_size = statistics.median(sizes)
    p90_size = sizes[int(len(sizes) * 0.9)]

    singles = [b for b in blocks if len(b.lines) == 1]
    median_line = statistics.median(b.bbox.height for b in singles) if singles else 0.0

    return {
        "blocks": len(blocks),
        "frag": sum(
            1 for b in blocks if b.text.strip()[:1].islower() and len(b.text.strip()) > 30
        ),
        "size_spread": (p90_size / median_size) if median_size else 0.0,
        "tall": sum(1 for b in singles if median_line and b.bbox.height > median_line * 1.6),
        "lowconf": sum(1 for b in blocks if b.confidence < 0.80),
        "chars": sum(len(b.text) for b in blocks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(r"C:\PhoneLink\computer-systems-Architecture.pdf"))
    parser.add_argument("--pages", default=",".join(str(p) for p in DEFAULT_PAGES))
    parser.add_argument("--work", type=Path, default=Path("_artifacts/eval"))
    parser.add_argument(
        "--classify",
        metavar="MODEL",
        help="ask this vision model what each region is (see ocr/layout_vlm.py)",
    )
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    args = parser.parse_args()

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    args.work.mkdir(parents=True, exist_ok=True)

    classifier = None
    if args.classify:
        from layoutkeep.ocr.layout_vlm import openai_vision_chat

        classifier = openai_vision_chat(args.base_url, args.classify)

    rows: list[tuple[int, dict[str, float]]] = []
    with pymupdf.open(str(args.source)) as src:
        for human in pages:
            one = args.work / f"p{human}.pdf"
            if not one.exists():
                part = pymupdf.open()
                part.insert_pdf(src, from_page=human - 1, to_page=human - 1)
                part.save(str(one))
                part.close()
            rows.append((human, measure_page(one, classifier)))

    _say(f"{'page':>5} {'blocks':>6} {'frag':>4} {'spread':>6} {'tall':>4} {'lowconf':>7} {'chars':>6}")
    for human, m in rows:
        _say(
            f"{human:5d} {m['blocks']:6.0f} {m['frag']:4.0f} {m['size_spread']:6.2f} "
            f"{m['tall']:4.0f} {m['lowconf']:7.0f} {m['chars']:6.0f}"
        )

    def total(key: str) -> float:
        return sum(m[key] for _p, m in rows)

    _say("")
    _say(f"TOTAL blocks {total('blocks'):.0f}  frag {total('frag'):.0f}  "
         f"tall {total('tall'):.0f}  lowconf {total('lowconf'):.0f}  chars {total('chars'):.0f}")
    spreads = [m["size_spread"] for _p, m in rows if m["size_spread"]]
    if spreads:
        _say(f"size_spread  median {statistics.median(spreads):.2f}  max {max(spreads):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
