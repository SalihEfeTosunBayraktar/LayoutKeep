"""Which text is better on a searchable scan: the file's own invisible OCR layer, or our OCR?

A searchable scan carries two readings of every page: the invisible layer the publisher's OCR left
(archive.org's "Text PDF"), and what our recogniser reads from the image. The reader uses ours.
Electricity in Agriculture's running header came out of ours as "APYJIN" and of the layer as the
title, so the header was never translated - and no loss criterion notices an untranslated line that
is not recognisable English.

With no transcription to compare against, both readings are scored against an English vocabulary
taken from the born-digital campaign books' text layers: the share of words (3+ letters) a reading
has that are known words. Unknown words in old technical prose count against both sources alike;
recognition noise counts against the one that produced it.

    python tools/audit/ocr_source_compare.py --every 10 --out tests/layout_eval/2026-09-17_ocr_source
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

from layoutkeep.ocr.layout_detector import load_detector
from layoutkeep.readers.pdf_reader import read_pdf

_WORD = re.compile(r"[A-Za-z]{3,}")
_RUNS = Path("_artifacts/campaign/runs")
_VOCABULARY_BOOKS = ("nist", "time_machine", "think_python")
_SCANNED_BOOKS = ("electricity_1922", "popular_science_1920")


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text)]


def _vocabulary() -> set[str]:
    seen: Counter[str] = Counter()
    for book in _VOCABULARY_BOOKS:
        for chunk in sorted((_RUNS / book / "src").glob("chunk_*.pdf")):
            with pymupdf.open(str(chunk)) as doc:
                for page in doc:
                    seen.update(_words(page.get_text()))
    return set(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--every", type=int, default=10, help="compare every Nth page")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    vocabulary = _vocabulary()
    detector = load_detector()
    rows = []
    for book in _SCANNED_BOOKS:
        for chunk in sorted((_RUNS / book / "src").glob("chunk_*.pdf"))[:: args.every]:
            doc = read_pdf(chunk, layout=detector)
            if not doc.pages or not doc.pages[0].scanned:
                continue
            with pymupdf.open(str(chunk)) as source:
                layer = _words(source[0].get_text())
            ours = _words(" ".join(b.text for b in doc.pages[0].blocks))
            if len(layer) < 20 or len(ours) < 20:
                continue
            rows.append({
                "book": book, "chunk": chunk.stem,
                "layer_words": len(layer), "layer_known": sum(w in vocabulary for w in layer),
                "ours_words": len(ours), "ours_known": sum(w in vocabulary for w in ours),
            })
            r = rows[-1]
            print(f"{book} {chunk.stem}: layer {r['layer_known']}/{r['layer_words']} "
                  f"ours {r['ours_known']}/{r['ours_words']}", flush=True)

    summary = {}
    for book in _SCANNED_BOOKS:
        mine = [r for r in rows if r["book"] == book]
        if not mine:
            continue
        summary[book] = {
            "pages": len(mine),
            "layer_known_share": sum(r["layer_known"] for r in mine) / sum(r["layer_words"] for r in mine),
            "ours_known_share": sum(r["ours_known"] for r in mine) / sum(r["ours_words"] for r in mine),
            "pages_layer_better": sum(
                r["layer_known"] / r["layer_words"] > r["ours_known"] / r["ours_words"] for r in mine
            ),
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ocr_source_compare.json").write_text(
        json.dumps({"vocabulary": len(vocabulary), "summary": summary, "pages": rows}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"vocabulary": len(vocabulary), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
