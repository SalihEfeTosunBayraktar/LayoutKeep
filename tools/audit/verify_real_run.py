"""Verify the real gemma outputs: read each translated file back, count what
survived, and compare against the source document.

Writes _artifacts/output/faz1-real/verify.json with per-pair before/after counts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from layoutkeep.writers.converter import read_any_document  # noqa: E402


def count_document(path: Path) -> dict:
    doc = read_any_document(path)
    pages = len(doc.pages)
    blocks = sum(len(p.blocks) for p in doc.pages)
    text = "\n".join(b.text for _, b in doc.iter_blocks())
    chars = len(text.replace(" ", "").replace("\n", ""))
    words = len(text.split())
    images = sum(len(page.images) for page in doc.pages)
    styled = sum(
        1
        for _, block in doc.iter_blocks()
        for line in block.lines
        for span in line.spans
        if span.style.bold or span.style.italic
    )
    return {
        "pages": pages, "blocks": blocks, "characters": chars,
        "words": words, "images": images, "styled_runs": styled,
    }


PAIRS = [
    # prose-only sources (original run)
    ("sample_report.pdf", "report.tr.pdf", "pdf->pdf"),
    ("sample_report.pdf", "report.tr.docx", "pdf->docx"),
    ("sample.epub", "sample.tr.epub", "epub->epub"),
    ("battery_test_report.docx", "battery.tr.docx", "docx->docx"),
    ("battery_test_report.png", "battery-from-png.tr.docx", "png->docx"),
    # rich sources: charts, photos, tables (2026-09-12)
    ("rich_report.pdf", "rich.tr.pdf", "pdf->pdf"),
    ("rich_report.pdf", "rich.tr.docx", "pdf->docx"),
    ("rich_book.epub", "richepub.tr.epub", "epub->epub"),
    ("rich_report.docx", "richdocx.tr.docx", "docx->docx"),
    ("rich_report.png", "richpng.tr.docx", "png->docx"),
]

SRC_DIRS = [Path("tests/fixtures"), Path("docs/samples"), Path("_artifacts/input")]
OUT_DIR = Path("_artifacts/output/faz1-real")


def find_source(name: str) -> Path:
    for d in SRC_DIRS:
        p = d / name
        if p.exists():
            return p
    raise FileNotFoundError(name)


def ratio(after: int, before: int) -> str:
    if before == 0:
        return "n/a" if after == 0 else f"+{after}"
    return f"{100 * after / before:.0f}%"


def main() -> None:
    results = []
    for src_name, out_name, label in PAIRS:
        src = find_source(src_name)
        out = OUT_DIR / out_name
        if not out.exists():
            results.append({"pair": label, "error": f"missing output {out_name}"})
            continue
        before = count_document(src)
        after = count_document(out)
        results.append({
            "pair": label,
            "source": src_name,
            "output": out_name,
            "before": before,
            "after": after,
            "ratios": {k: ratio(after[k], before[k]) for k in before},
        })

    OUT_DIR.joinpath("verify.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for r in results:
        if "error" in r:
            print(f"ERR  {r['pair']}: {r['error']}")
            continue
        print(
            f"ok   {r['pair']:<12} chars {r['ratios']['characters']:<5}"
            f" words {r['ratios']['words']:<5} pages {r['ratios']['pages']:<5}"
            f" img {r['ratios']['images']:<5} styled {r['ratios']['styled_runs']}"
        )


if __name__ == "__main__":
    main()
