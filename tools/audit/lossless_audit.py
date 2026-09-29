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
    L9  no garbled letters             translated blocks with a word mixing in another alphabet's letter == 0
    L10 nothing drawn on a figure      words sitting inside a picture rather than beside it == 0
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
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from layoutkeep.core.docir import load_project
from layoutkeep.verify import (
    LOSS_KINDS,
    is_checked,
    is_untouched,
    ordinary_words,
    output_losses,
    overlapping_words,
    source_of,
    translation_losses,
    words,
)

#: review_reason stores the UIStrings key since the i18n pass; project files written before it
#: hold the plain Turkish sentence. Match both so old runs still audit.
_FIT_FAILED_MARKERS = ("REVIEW_FIT_FAILED", "çeviri kutuya sığmadı")


def _say(line: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding) + chr(10))


def audit_chunk(src: Path, out: Path, project: Path, target_lang: str = "tr") -> dict:
    """The loss criteria from `layoutkeep.verify` - the ones the application runs - plus D1-D3."""

    doc = load_project(project)
    found: dict[str, list[str]] = {k: [] for k in (*LOSS_KINDS, "D1", "D2", "D3")}
    blocks = {b.id: b for _, b in doc.iter_blocks()}

    def tag(page: int) -> str:
        ref = doc.pages[page].source_ref if page >= 0 else "0"
        return f"{src.stem} p{int(ref) + 1}"

    for loss in translation_losses(doc, target_lang) + output_losses(src, out, doc):
        if loss.kind == "L1":
            found["L1"].append(loss.detail)
        elif loss.kind in ("L2", "L3", "L6", "L9"):
            found[loss.kind].append(f"{tag(loss.page)}: {blocks[loss.block_ids[0]].text[:90]!r}")
        else:
            found[loss.kind].append(f"{tag(loss.page)}: {loss.detail}")

    checked = 0
    with pymupdf.open(str(out)) as output:
        for index, page_data in enumerate(doc.pages):
            number = int(page_data.source_ref)
            if number < output.page_count:
                squeezed, _ = overlapping_words(output[number].get_text("words"), same_block=True)
                if squeezed:
                    found["D3"].append(f"{tag(index)}: {squeezed} squeezed word pairs")
            for block in page_data.blocks:
                if not is_checked(block):
                    continue
                checked += 1
                sample = f"{tag(index)}: {block.text[:90]!r}"
                source = source_of(block)
                if len(ordinary_words(source)) < 4 and is_untouched(block) and len(words(source)) >= 2:
                    # Too short to tell a name from an untranslated phrase without knowing the
                    # language: listed for a human, not counted as a loss or as a success.
                    found["D2"].append(sample)
                if any(marker in (block.review_reason or "") for marker in _FIT_FAILED_MARKERS):
                    found["D1"].append(sample)
    return {"counts": {"blocks": checked}, "found": found}


def audit_work(work: Path, target_lang: str = "tr") -> dict:
    totals = Counter()
    findings: dict[str, list[str]] = {k: [] for k in (*LOSS_KINDS, "D1", "D2", "D3")}
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
        if any(result["found"][k] for k in LOSS_KINDS):
            failing.append(index)
    source_chunks = len(list((work / "src").glob("chunk_*.pdf")))
    if len(chunks) != source_chunks:
        # A smoke run (`live_check --chunks N`) translates part of a document on purpose, so the
        # merged output holds fewer pages than the source and this is not a loss - but a *complete*
        # run that is missing chunks has lost pages, so the difference is always reported.
        findings["L1"].append(f"{source_chunks} source chunks, {len(chunks)} audited (partial run)")
    lossless = all(not findings[k] for k in LOSS_KINDS) and not missing
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
        ("L3", "text not on the page"),
        ("L4", "off the page"),
        ("L5", "markup leaked"),
        ("L6", "numbers lost"),
        ("L7", "text drawn over text"),
        ("L8", "untouched text moved"),
        ("L9", "garbled letters"),
        ("L10", "text drawn over a figure"),
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
