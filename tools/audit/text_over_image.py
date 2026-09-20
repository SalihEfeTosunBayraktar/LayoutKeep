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
from itertools import pairwise
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


def union_area(rects: list[pymupdf.Rect]) -> float:
    """Area covered by at least one of `rects` - exactly, by sweeping x-strips.

    Summing areas double-counts overlapping images; a grid would be O(pixels) per page for an
    answer that is only needed to one decimal place.
    """
    edges = sorted({edge for rect in rects for edge in (rect.x0, rect.x1)})
    total = 0.0
    for left, right in pairwise(edges):
        if right <= left:
            continue
        spans = sorted(
            (rect.y0, rect.y1) for rect in rects if rect.x0 < right and rect.x1 > left
        )
        height = 0.0
        top: float | None = None
        bottom: float | None = None
        for span_top, span_bottom in spans:
            if bottom is None or span_top > bottom:
                if bottom is not None and top is not None:
                    height += bottom - top
                top, bottom = span_top, span_bottom
            else:
                bottom = max(bottom, span_bottom)
        if bottom is not None and top is not None:
            height += bottom - top
        total += (right - left) * height
    return total


def figures(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """The images on a page that are pictures, not the scanned page itself.

    Measured on the 1907 cookbook: its pages carry the scan twice (a background and a cleaned
    layer) *plus* a dozen patches over the printed lines, none of them larger than 6% of the page
    on its own. Judging each image alone therefore reported 126 words "on top of a figure" on a
    document where every word sits on the scan by design. What says whether a page is a scan is
    the *union* of its images, not the largest of them.
    """
    page_area = max(1.0, page.rect.get_area())
    images = [pymupdf.Rect(info["bbox"]) for info in page.get_image_info()]
    if union_area(images) >= BACKGROUND * page_area:
        return []
    return [rect for rect in images if rect.get_area() < BACKGROUND * page_area]


def covered_words(pdf: Path) -> list[tuple[int, str, tuple[float, ...]]]:
    """Every word whose box sits mostly inside a figure on the same page."""
    hits: list[tuple[int, str, tuple[float, ...]]] = []
    with pymupdf.open(pdf) as document:
        for number, page in enumerate(document, start=1):
            hits.extend((number, word, box) for _, word, box in covered_words_page(page))
    return hits


def inherited_words(source: Path, written: Path) -> int:
    """Words the *source* already draws inside its own figures - chart labels, mostly.

    WHY THIS EXISTS: the arXiv page that reported 26 words "on top of a figure" has a bar chart
    whose values and category names are PDF text sitting on the plot image in the original: the
    source page counts 28 of them. Reporting that as a loss of ours is wrong twice over - nothing
    was lost, and the number does not move when the pipeline is fixed. A figure's own labels are
    its content, not text that strayed onto it.
    """
    if not source.exists() or not written.exists():
        return 0
    with pymupdf.open(source) as original, pymupdf.open(written) as translated:
        if original.page_count != translated.page_count:
            return 0
        return sum(len(covered_words_page(page)) for page in original)


def net_covered(source: Path | None, written: Path) -> tuple[int, int]:
    """(raw, net) for one written pdf: words over figures, and how many are ours.

    Subtracted per page, not per document: a chart on one page must not license stray text on
    another. `max(0, ...)` per page, because a page with fewer covered words than its source is
    not a credit to spend elsewhere.
    """
    raw = len(covered_words(written))
    if source is None or not source.exists():
        return raw, raw
    with pymupdf.open(source) as original, pymupdf.open(written) as translated:
        if original.page_count != translated.page_count:
            return raw, raw
        inherited = sum(
            min(len(covered_words_page(page)), len(covered_words_page(other_page)))
            for page, other_page in zip(original, translated, strict=False)
        )
    return raw, max(0, raw - inherited)


def covered_words_page(page: pymupdf.Page) -> list[tuple[int, str, tuple[float, ...]]]:
    """`covered_words` for one already-open page."""
    images = figures(page)
    if not images:
        return []
    hits: list[tuple[int, str, tuple[float, ...]]] = []
    for word in page.get_text("words"):
        box = pymupdf.Rect(word[:4])
        for image in images:
            overlap = box.intersect(image)
            if overlap.is_valid and overlap.get_area() > COVERED * box.get_area():
                hits.append((0, str(word[4]), tuple(round(v, 1) for v in box)))
                break
    return hits


def source_of(written: Path) -> Path | None:
    """The source page a written page came from: `out/t_0007.pdf` pairs with `src/chunk_0007.pdf`."""
    run = written.parent.parent
    chunk = run / "src" / written.name.replace("t_", "chunk_")
    return chunk if chunk.exists() else None


def scan(target: Path, verbose: bool = False) -> int:
    """Report every product of one run (or a single pdf) that covers an image with text.

    What the exit code counts is the **net** figure: the words this run draws over a figure that
    the source did not already draw there itself. The raw count is still printed - the difference
    between the two is what says whether a page changed at all.
    """
    pdfs = (
        sorted(target.glob("t_*.pdf")) or sorted(target.glob("*.pdf"))
        if target.is_dir()
        else [target]
    )
    total = 0
    for pdf in pdfs:
        hits = covered_words(pdf)
        if not hits:
            continue
        source = source_of(pdf) if target.is_dir() else None
        raw, net = net_covered(source, pdf)
        total += net
        note = f" (kaynakta karsiligi var, net {net})" if source is not None and net != raw else ""
        print(f"{pdf.name}: {len(hits)} kelime gorselin ustunde{note}")
        if verbose:
            for number, word, box in hits[:8]:
                print(f"    p{number} '{word}' @ {box}")
    print(f"{target.name}: toplam {total} kelime gorselin ustunde")
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
