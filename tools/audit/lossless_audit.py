"""Is a translated document lossless? Measured on the output, against what was actually sent.

The criteria are defined in `docs/campaign/JOURNAL.md`:

    L1  same pages                     output page count == source page count
    L2  nothing left untranslated      translatable blocks still in the source language == 0
    L3  nothing dropped by the writer  translated blocks whose words are missing from the page == 0
    L4  nothing drawn off the page     words outside the page box == 0
    L5  no markup leaked               tags in the output that are not in the source == 0
    L6  no numbers lost                numbers of the source missing from the translation == 0
    D1  readability (reported only)    blocks drawn below the readability floor
    D2  for review (reported only)     short blocks left unchanged: names, or untranslated phrases

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

from layoutkeep.core.copies import drops_numbers, is_copy, is_identical, ordinary_words
from layoutkeep.core.docir import load_project
from layoutkeep.core.protect import is_data_only
from layoutkeep.writers.pdf_writer import is_wordless

#: Words that mark a text as still English. Common enough that any English sentence carries
#: several, and not words of the target language, so a share of them in a written block means
#: the block (or a large part of it) was not translated - including partial translations, which
#: an identity check alone misses.
_ENGLISH = frozenset(
    [
        "the",
        "and",
        "of",
        "to",
        "is",
        "in",
        "that",
        "with",
        "for",
        "are",
        "this",
        "which",
        "by",
        "be",
        "as",
        "on",
        "an",
        "or",
        "from",
        "it",
        "its",
        "was",
        "were",
        "can",
        "will",
        "not",
        "but",
        "have",
        "has",
    ]
)
_ENGLISH_SHARE = 0.2
_ENGLISH_MIN_WORDS = 5

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



def audit_chunk(src: Path, out: Path, project: Path) -> dict:
    doc = load_project(project)
    found: dict[str, list[str]] = {k: [] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "D1", "D2")}
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
            for match in _MARKUP.finditer(page.get_text()):
                if match.group(0).casefold() not in source_markup:
                    found["L5"].append(f"{tag}: {match.group(0)!r}")

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
                ordinary = ordinary_words(written)
                english = (
                    len(ordinary) >= _ENGLISH_MIN_WORDS
                    and sum(w in _ENGLISH for w in ordinary) / len(ordinary) >= _ENGLISH_SHARE
                )
                # Prose is judged on ordinary words (core.copies): names, brands, addresses and
                # quoted strings legitimately survive translation and must not count against it.
                if len(ordinary_words(source_text)) >= 4:
                    if untouched or english or is_copy(source_text, written):
                        found["L2"].append(sample)
                elif untouched and len(source_words) >= 2:
                    # Too short to tell a name from an untranslated phrase without knowing the
                    # language: listed for a human, not counted as a loss or as a success.
                    found["D2"].append(sample)

                if written_words:
                    need = Counter(written_words)
                    present = sum(min(n, on_page[w]) for w, n in need.items())
                    if present / sum(need.values()) < _PRESENT_SHARE:
                        found["L3"].append(sample)

                if block.source_text and drops_numbers(source_text, written):
                    found["L6"].append(sample)

                if _FIT_FAILED in (block.review_reason or ""):
                    found["D1"].append(sample)

    return {"counts": dict(counts), "found": found}


def audit_work(work: Path) -> dict:
    totals = Counter()
    findings: dict[str, list[str]] = {k: [] for k in ("L1", "L2", "L3", "L4", "L5", "L6", "D1", "D2")}
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
        result = audit_chunk(src, out, project)
        totals.update(result["counts"])
        for key, items in result["found"].items():
            findings[key].extend(items)
        if any(result["found"][k] for k in ("L1", "L2", "L3", "L4", "L5", "L6")):
            failing.append(index)
    source_chunks = len(list((work / "src").glob("chunk_*.pdf")))
    if len(chunks) != source_chunks:
        findings["L1"].append(f"{source_chunks} source chunks, {len(chunks)} audited")
    lossless = all(not findings[k] for k in ("L1", "L2", "L3", "L4", "L5", "L6")) and not missing
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
    args = parser.parse_args()

    result = audit_work(args.work)
    _say(f"work      {args.work}")
    _say(f"chunks    {result['chunks']}   translatable prose blocks {result['blocks']}")
    for key, label in (
        ("L1", "same pages"),
        ("L2", "left untranslated"),
        ("L3", "dropped by writer"),
        ("L4", "off the page"),
        ("L5", "markup leaked"),
        ("L6", "numbers lost"),
        ("D1", "below readability floor"),
        ("D2", "short blocks left unchanged"),
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
