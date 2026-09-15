"""How much of a translated document is actually translated, and how much still fits.

The CLI's own `translated N/M` line counts requests that came back, not requests that came back
*translated*: a model that echoes its input verbatim is counted as a success. On the first real
run of `computer-systems-Architecture.pdf` that line read 193/210 while a quarter of the prose
on the page was still English - the pages looked translated at a glance and were not.

This measures the output instead of the pipeline's opinion of it:

  * **untranslated** - a source segment that appears verbatim in the output. Some of these are
    correct (a Boolean expression, a part number); the point is the number, tracked between
    models and runs, not any single line.
  * **overflow** - a block whose text no longer fits the box it came from, which is the other
    half of "layout preserved".

Both are computed by re-reading the source through the same reader the translation used, so the
comparison is against what was actually sent, not against a fresh guess at the source text.

    python tools/audit/translation_completeness.py SOURCE.pdf TRANSLATED.pdf
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pymupdf

from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import measure_fit

#: Shorter than this a segment is a label, a number or a fragment - too short for "does this
#: string still appear in the output" to mean anything (every document contains "the").
MIN_PROSE_CHARS = 25


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def report(source: Path, translated: Path) -> dict[str, float]:
    doc = read_pdf(source)
    with pymupdf.open(str(translated)) as out:
        out_text = _normalise(" ".join(page.get_text() for page in out))

    prose = [
        block
        for _page, block in doc.iter_blocks()
        if block.translatable and len(block.text) >= MIN_PROSE_CHARS
    ]
    untranslated = [b for b in prose if _normalise(b.text) in out_text]

    translatable = [b for _p, b in doc.iter_blocks() if b.translatable]
    overflowing = [
        b
        for b in translatable
        if not measure_fit(b.text, b.dominant_style(), b.bbox, rotation=b.rotation)[0]
    ]

    stats = {
        "prose_segments": len(prose),
        "untranslated": len(untranslated),
        "untranslated_pct": 100.0 * len(untranslated) / max(1, len(prose)),
        "translatable": len(translatable),
        "source_overflow": len(overflowing),
    }
    print(f"source      {source}")
    print(f"translated  {translated}")
    print(f"prose segments (>= {MIN_PROSE_CHARS} chars)  {stats['prose_segments']}")
    print(
        f"still verbatim source text            {stats['untranslated']} "
        f"({stats['untranslated_pct']:.0f}%)"
    )
    print(f"source blocks that do not fit         {stats['source_overflow']} / {stats['translatable']}")
    if untranslated:
        print("examples:")
        for block in untranslated[:10]:
            print(f"  {_normalise(block.text)[:78]}")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("translated", type=Path)
    args = parser.parse_args()
    report(args.source, args.translated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
