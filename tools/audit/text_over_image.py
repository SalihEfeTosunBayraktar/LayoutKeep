"""How many words does a run draw on top of an image?

WHY THIS EXISTS: the audit's L7 counts text drawn over *text*, and a Wikipedia run scored L7=0
while 87 of its words sat on top of a photograph. The cause is a bounding box, not a translation:
PyMuPDF reports a text block as the union of the lines that wrap around a figure, so a block whose
real lines stop short of the picture is handed to the writer as a box that covers it - and
`insert_htmlbox` then flows the translation across the whole width. The reader cannot see it, the
audit did not look for it, and the page is unreadable.

Usage:  python tools/audit/text_over_image.py <run dir or pdf> [--verbose]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

#: Share of a word's area that must fall inside an image before it counts as covered. A glyph box
#: that merely touches a picture's edge is not a loss; one that sits in it is.
COVERED = 0.55

#: Share of the page an image must cover before it counts as the page's own background rather than
#: a figure. A scanned document is one big image with the translation written over it by design -
#: counting that would report every word of every scan. Figures are the pictures a reader would
#: notice text sitting on.
BACKGROUND = 0.85


def figures(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """The images on a page that are pictures, not the scanned page itself."""
    page_area = max(1.0, page.rect.get_area())
    return [
        rect
        for info in page.get_image_info()
        if (rect := pymupdf.Rect(info["bbox"])).get_area() < BACKGROUND * page_area
    ]


def covered_words(pdf: Path) -> list[tuple[int, str, tuple[float, ...]]]:
    """Every word whose box sits mostly inside a figure on the same page."""
    hits: list[tuple[int, str, tuple[float, ...]]] = []
    with pymupdf.open(pdf) as document:
        for number, page in enumerate(document, start=1):
            images = figures(page)
            if not images:
                continue
            for word in page.get_text("words"):
                box = pymupdf.Rect(word[:4])
                for image in images:
                    overlap = box.intersect(image)
                    if overlap.is_valid and overlap.get_area() > COVERED * box.get_area():
                        hits.append((number, str(word[4]), tuple(round(v, 1) for v in box)))
                        break
    return hits


def scan(target: Path, verbose: bool = False) -> int:
    """Report every product of one run (or a single pdf) that covers an image with text."""
    pdfs = sorted(target.glob("t_*.pdf")) or sorted(target.glob("*.pdf")) if target.is_dir() else [target]
    total = 0
    for pdf in pdfs:
        if pdf.name.endswith(".tr.pdf") and not (target.is_dir() and list(target.glob("t_*.pdf"))):
            hits = covered_words(pdf)
        else:
            hits = covered_words(pdf)
        if hits:
            total += len(hits)
            print(f"{pdf.name}: {len(hits)} kelime görselin üstünde")
            if verbose:
                for number, word, box in hits[:8]:
                    print(f"    p{number} '{word}' @ {box}")
    print(f"\n{target.name}: toplam {total} kelime görselin üstünde")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="koşu dizini (out/ ile) ya da tek bir PDF")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    target = args.target
    if (target / "out").is_dir():
        target = target / "out"
    return 0 if scan(target, args.verbose) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
