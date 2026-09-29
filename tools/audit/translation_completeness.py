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
import sys
from pathlib import Path

import pymupdf

from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import measure_fit

#: Shorter than this a segment is a label, a number or a fragment - too short for "does this
#: string still appear in the output" to mean anything (every document contains "the").
MIN_PROSE_CHARS = 25


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _say(line: str) -> None:
    """Print a line that may contain any character, on any console.

    The report died halfway through its own output on a Windows cp1254 terminal: the examples it
    prints are document text, so the first Turkish character it reached raised
    UnicodeEncodeError and took the remaining measurements with it.
    """
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


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

    # Overflow on the OUTPUT, not just the source geometry: text the writer placed outside the
    # page is overflow a reader would actually see. Measured per page against its own rect,
    # with a small tolerance for the glyph box's anti-aliased edge.
    off_page = 0
    with pymupdf.open(str(translated)) as out:
        for page in out:
            # One point of tolerance each way: a glyph box's anti-aliased edge is not overflow.
            rect = page.rect
            limit = pymupdf.Rect(rect.x0 - 1.0, rect.y0 - 1.0, rect.x1 + 1.0, rect.y1 + 1.0)
            for x0, y0, x1, y1, *_rest in page.get_text("words"):
                if x0 < limit.x0 or y0 < limit.y0 or x1 > limit.x1 or y1 > limit.y1:
                    off_page += 1

    stats = {
        "off_page_words": off_page,
        "prose_segments": len(prose),
        "untranslated": len(untranslated),
        "untranslated_pct": 100.0 * len(untranslated) / max(1, len(prose)),
        "translatable": len(translatable),
        "source_overflow": len(overflowing),
    }
    _say(f"source      {source}")
    _say(f"translated  {translated}")
    _say(f"prose segments (>= {MIN_PROSE_CHARS} chars)  {stats['prose_segments']}")
    _say(
        f"still verbatim source text            {stats['untranslated']} "
        f"({stats['untranslated_pct']:.0f}%)"
    )
    _say(f"source blocks that do not fit         {stats['source_overflow']} / {stats['translatable']}")
    _say(f"words drawn outside the page          {stats['off_page_words']}")
    if untranslated:
        _say("examples:")
        for block in untranslated[:10]:
            _say(f"  {_normalise(block.text)[:78]}")
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
