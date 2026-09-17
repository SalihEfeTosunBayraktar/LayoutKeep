"""Is a translated document lossless? Measured on the output, against what was actually sent.

The criteria are defined in `docs/campaign/JOURNAL.md`:

    L1  same pages                     output page count == source page count
    L2  nothing left untranslated      blocks still in the source, or in another language than the target == 0
    L3  nothing dropped by the writer  translated blocks whose words are missing from the page == 0
    L4  nothing drawn off the page     words outside the page box == 0
    L5  no markup leaked               tags in the output that are not in the source == 0
    L6  no numbers lost                numbers of the source missing from the translation == 0
    L7  nothing drawn over text        pages with words of one block drawn over another's == 0
    L8  nothing untouched moved        digital pages where text no translated block covers is not where it was == 0
    D1  readability (reported only)    blocks drawn below the readability floor
    D2  for review (reported only)     short blocks left unchanged: names, or untranslated phrases
    D3  legibility (reported only)     pages where a block's own lines are squeezed into each other

It reads a `translate_book.py` work directory, where every chunk left its source (`src/`), its
output and its project file (`out/t_NNNN.pdf`, `out/t_NNNN.lkproj`). The project records which
blocks were translatable, what their source was and what was written - so the audit judges the
pipeline's real inputs and outputs, and never has to re-read or re-OCR the source.

    python tools/audit/lossless_audit.py --work _artifacts/campaign/book --json result.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from layoutkeep.core.copies import drops_numbers, is_copy, is_identical, ordinary_words, wrong_language
from layoutkeep.core.docir import load_project
from layoutkeep.core.protect import is_data_only
from layoutkeep.writers.pdf_writer import is_wordless

#: A block counts as present on its page when this share of its words are found there. Below 1.0
#: because the renderer may hyphenate a long word across a line break, which splits one token in
#: two.
_PRESENT_SHARE = 0.9

_FIT_FAILED = "çeviri kutuya sığmadı"
_MARKUP = re.compile(r"</?[A-Za-z][A-Za-z0-9_]*\s*/?>|<\d+>|</\d+>|</?text\b", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_INLINE_MARKER = re.compile(r"<(/?)(\d+)>")


def _say(line: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text.replace("­", ""))]



#: Two words from different lines overlapping by more than this share of the smaller one cannot
#: both be read. Measured: a magazine page with blocks drawn over each other had 17 such pairs; a
#: clean novel page, a contents page, a scanned book page and the source PDF itself had 0.
_OVERLAP_SHARE = 0.3

#: Height below which a drawn word is not legible text in the first place.
_LEGIBLE_PT = 5.0


def _overlapping_words(words: list, *, same_block: bool = False) -> int:
    """Pairs of words from different lines drawn over each other.

    `same_block=False` counts words of different blocks - one text drawn over another (L7).
    `same_block=True` counts lines of one block squeezed into each other - text forced into a box
    far too small, typically recognition noise from a decorative advert (D3).
    """
    # Only legible words count: text under _LEGIBLE_PT tall is already below the readability floor
    # (D1) - on the magazine it is recognition noise from adverts ("AR", "STW") - and two such
    # scraps touching is not one text drawn over another.
    boxes = [
        (pymupdf.Rect(w[:4]), w[5], (w[5], w[6]))
        for w in words
        if len(w[4]) > 1 and (w[3] - w[1]) >= _LEGIBLE_PT
    ]
    pairs = 0
    for i, (a, block_a, line_a) in enumerate(boxes):
        for b, block_b, line_b in boxes[i + 1:]:
            if line_a == line_b or (block_a == block_b) != same_block:
                continue
            inter = a & b
            if inter.is_empty:
                continue
            smaller = min(a.get_area(), b.get_area())
            if smaller > 0 and inter.get_area() / smaller > _OVERLAP_SHARE:
                pairs += 1
    return pairs


def _kept_text_moved(source_page: pymupdf.Page, output_page: pymupdf.Page, page_data) -> int:
    """Source text runs that no translated block covers, and that are not where they were.

    Nothing the pipeline did not translate should move. Think Python's Figure 3.1 did - redaction
    elsewhere on the page shifted 8 of its 11 labels - and only the two pages where the shift made
    words overlap showed up, as L7. Compared on born-digital pages, where the source has text.
    """
    import re as _re

    changed = [
        pymupdf.Rect(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
        for b in page_data.blocks
        if b.translatable
        and not (b.source_text and _re.sub(r"</?\d+>", "", b.source_text).split() == b.text.split())
    ]
    grown = [pymupdf.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2) for r in changed]

    def runs(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
        return [
            (s["text"].strip(), pymupdf.Rect(s["bbox"]))
            for b in page.get_text("dict")["blocks"] if b["type"] == 0
            for line in b["lines"] for s in line["spans"] if s["text"].strip()
        ]

    out = runs(output_page)
    moved = 0
    for text, rect in runs(source_page):
        if any(r.intersects(rect) for r in grown):
            continue
        # Half a line of the run's own height: a kept block redrawn because a neighbour's clearing
        # reached it lands a point or two off (NIST's author names, 2-3 pt), which is not damage;
        # Figure 3.1's labels dropped 10-11 pt, a whole line.
        tolerance = max(1.0, rect.height / 2)
        if not any(
            t == text and abs(o.x0 - rect.x0) <= tolerance and abs(o.y0 - rect.y0) <= tolerance
            for t, o in out
        ):
            moved += 1
    return moved


def audit_chunk(src: Path, out: Path, project: Path, target_lang: str = "tr") -> dict:
    doc = load_project(project)
    found: dict[str, list[str]] = {k: [] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "D1", "D2", "D3")}
    counts = Counter()

    with pymupdf.open(str(src)) as source, pymupdf.open(str(out)) as output:
        if source.page_count != output.page_count:
            found["L1"].append(f"{source.page_count} source pages, {output.page_count} output")
        source_markup = {
            m.group(0).casefold() for page in source for m in _MARKUP.finditer(page.get_text())
        }

        for page_data in doc.pages:
            index = int(page_data.source_ref)
            if index >= output.page_count:
                continue
            page = output[index]
            rect = page.rect
            words = page.get_text("words")
            on_page = Counter(
                w.casefold() for word in words for w in _WORD.findall(word[4].replace("­", ""))
            )
            tag = f"{src.stem} p{index + 1}"

            for word in words:
                x0, y0, x1, y1 = word[:4]
                if x1 < rect.x0 - 1 or x0 > rect.x1 + 1 or y1 < rect.y0 - 1 or y0 > rect.y1 + 1:
                    found["L4"].append(f"{tag}: {word[4]!r}")
            overlapping = _overlapping_words(words)
            if overlapping:
                found["L7"].append(f"{tag}: {overlapping} overlapping word pairs")
            squeezed = _overlapping_words(words, same_block=True)
            if squeezed:
                found["D3"].append(f"{tag}: {squeezed} squeezed word pairs")
            for match in _MARKUP.finditer(page.get_text()):
                if match.group(0).casefold() not in source_markup:
                    found["L5"].append(f"{tag}: {match.group(0)!r}")

            if not page_data.scanned:
                moved = _kept_text_moved(source[index], page, page_data)
                if moved:
                    found["L8"].append(f"{tag}: {moved} untouched text runs moved")

            for block in page_data.blocks:
                if not block.translatable:
                    continue
                source_text = (
                    _INLINE_MARKER.sub("", block.source_text) if block.source_text else block.text
                )
                written = block.text
                if is_data_only(source_text) or is_wordless(block):
                    continue
                counts["blocks"] += 1
                source_words = _words(source_text)
                written_words = _words(written)
                sample = f"{tag}: {written[:90]!r}"

                untouched = not block.source_text or is_identical(source_text, written)
                # Prose is judged on ordinary words (core.copies): names, brands, addresses and
                # quoted strings legitimately survive translation and must not count against it.
                if len(ordinary_words(source_text)) >= 4:
                    wrong = wrong_language(written, target_lang) if target_lang else None
                    if untouched or wrong or is_copy(source_text, written):
                        found["L2"].append(sample)
                elif untouched and len(source_words) >= 2:
                    # Too short to tell a name from an untranslated phrase without knowing the
                    # language: listed for a human, not counted as a loss or as a success.
                    found["D2"].append(sample)

                # An unchanged block on a scanned page is not drawn: its text is the scan's pixels,
                # and the invisible layer holds whatever that page's own OCR read there (Electricity
                # chunk 0020: our OCR read the running header as "APYJIN", the layer as the title).
                if written_words and not (page_data.scanned and untouched):
                    need = Counter(written_words)
                    present = sum(min(n, on_page[w]) for w, n in need.items())
                    if present / sum(need.values()) < _PRESENT_SHARE:
                        found["L3"].append(sample)

                if block.source_text and drops_numbers(source_text, written, target_lang):
                    found["L6"].append(sample)

                if _FIT_FAILED in (block.review_reason or ""):
                    found["D1"].append(sample)

    return {"counts": dict(counts), "found": found}


def audit_work(work: Path, target_lang: str = "tr") -> dict:
    totals = Counter()
    findings: dict[str, list[str]] = {k: [] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "D1", "D2", "D3")}
    chunks = sorted((work / "out").glob("t_*.lkproj"))
    missing = []
    failing: list[str] = []
    for project in chunks:
        index = project.stem.split("_")[1]
        src = work / "src" / f"chunk_{index}.pdf"
        out = project.with_suffix(".pdf")
        if not (src.exists() and out.exists()):
            missing.append(project.stem)
            continue
        result = audit_chunk(src, out, project, target_lang)
        totals.update(result["counts"])
        for key, items in result["found"].items():
            findings[key].extend(items)
        if any(result["found"][k] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")):
            failing.append(index)
    source_chunks = len(list((work / "src").glob("chunk_*.pdf")))
    if len(chunks) != source_chunks:
        findings["L1"].append(f"{source_chunks} source chunks, {len(chunks)} audited")
    lossless = all(not findings[k] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")) and not missing
    return {
        "chunks": len(chunks),
        "blocks": totals["blocks"],
        "counts": {k: len(v) for k, v in findings.items()},
        "lossless": lossless,
        "missing_outputs": missing,
        # Every chunk with a loss, so a repair pass can re-translate exactly those.
        "failing_chunks": failing,
        "examples": {k: v[:15] for k, v in findings.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--to", default="tr", help="target language, for the wrong-language check")
    args = parser.parse_args()

    result = audit_work(args.work, args.to)
    _say(f"work      {args.work}")
    _say(f"chunks    {result['chunks']}   translatable prose blocks {result['blocks']}")
    for key, label in (
        ("L1", "same pages"),
        ("L2", "left untranslated"),
        ("L3", "dropped by writer"),
        ("L4", "off the page"),
        ("L5", "markup leaked"),
        ("L6", "numbers lost"),
        ("L7", "text drawn over text"),
        ("L8", "untouched text moved"),
        ("D1", "below readability floor"),
        ("D2", "short blocks left unchanged"),
        ("D3", "text squeezed in its box"),
    ):
        _say(f"{key}  {label:<26} {result['counts'][key]}")
        for example in result["examples"][key][:5]:
            _say(f"      {example}")
    _say(f"LOSSLESS  {'YES' if result['lossless'] else 'NO'}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["lossless"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
