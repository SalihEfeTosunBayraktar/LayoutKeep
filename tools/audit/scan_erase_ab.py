"""Does the coloured-panel rule touch ordinary scanned pages?

D-012 turned a saturated box's ink-erasing off, so the caller paints its rectangle instead. On a
cover that is the point; on an ordinary scanned page it could mean a flat patch where the ink eraser
used to leave paper. This renders the same interior pages of a real scanned book twice - rule on and
rule off - and compares them with the source, so the answer is pixels, not opinion.

    .venv/Scripts/python tools/audit/scan_erase_ab.py <book.pdf> [pages...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import layoutkeep.writers.pdf_writer as writer  # noqa: E402
from layoutkeep.core.docir import apply_segments, segments_from_document  # noqa: E402
from layoutkeep.readers.pdf_reader import read_pdf  # noqa: E402

OUT = Path(__import__("os").environ["LOCALAPPDATA"]) / "Temp" / "lk_scan_ab"
DPI = 150


def render(path: Path, page_index: int) -> np.ndarray:
    page = pymupdf.open(path)[page_index]
    pixmap = page.get_pixmap(dpi=DPI)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)[:, :, :3]


def write_one(book: Path, page_index: int, tag: str, threshold: int) -> Path:
    writer._SCAN_PAPER_MAX_SATURATION = threshold
    document = read_pdf(book)
    document.pages = document.pages[page_index : page_index + 1]
    segments = segments_from_document(document)
    for segment in segments:
        segment.target = f"ceviri {tag}"
    apply_segments(document, segments)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{book.stem}_{page_index}_{tag}.pdf"
    writer.write_pdf(document, book, target)
    return target


def main() -> int:
    book = Path(sys.argv[1])
    pages = [int(v) - 1 for v in sys.argv[2:]] or [3, 7, 11]
    print(f"{book.name}: {len(pages)} sayfa, dpi={DPI}")
    print(f"{'sayfa':>5} · {'kural=120 fark':>13} · {'kural=255 fark':>13} · {'iki kural farki':>15}")
    for index in pages:
        source = render(book, index)
        on = render(write_one(book, index, "acik", 120), index)
        off = render(write_one(book, index, "kapali", 255), index)
        if on.shape != source.shape or off.shape != source.shape:
            print(f"{index + 1:>5} · boyut uyusmuyor, atlandi")
            continue
        on_diff = int((np.abs(on.astype(int) - source.astype(int)).max(2) > 24).sum())
        off_diff = int((np.abs(off.astype(int) - source.astype(int)).max(2) > 24).sum())
        between = int((np.abs(on.astype(int) - off.astype(int)).max(2) > 24).sum())
        total = source.shape[0] * source.shape[1]
        print(
            f"{index + 1:>5} · {on_diff:>6} (%{100 * on_diff / total:4.1f}) · "
            f"{off_diff:>6} (%{100 * off_diff / total:4.1f}) · {between:>8} (%{100 * between / total:4.1f})"
        )
    print(f"\ncikti: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
