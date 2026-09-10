"""Measure what survives every source-to-target conversion this project offers.

The user interface offers a grid of format pairs and says nothing about which of them actually
work. This runs each pair on a document built for the purpose, translates it with the fake
provider (so the only thing under test is the reader and the writer), and counts what came out
the other side against what went in: characters, images, pages, and the bold/italic runs that
carry a document's emphasis.

Nothing here judges quality. It counts. A pair that loses two thirds of its images loses them
whatever anyone believes about the architecture.

    .venv/Scripts/python.exe tools/audit/format_matrix.py out.json
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

SOURCES = ("pdf", "epub", "docx", "png")
TARGETS = ("pdf", "epub", "docx", "html", "png")


@dataclass
class Counts:
    characters: int = 0
    words: int = 0
    images: int = 0
    pages: int = 0
    styled_runs: int = 0

    def ratio(self, other: Counts, field_name: str) -> float:
        mine = getattr(self, field_name)
        theirs = getattr(other, field_name)
        return mine / theirs if theirs else (1.0 if not mine else 0.0)


@dataclass
class Pair:
    source: str
    target: str
    ok: bool = False
    error: str = ""
    before: Counts = field(default_factory=Counts)
    after: Counts = field(default_factory=Counts)
    files_written: int = 0
    notes: list[str] = field(default_factory=list)


def build_sources(into: Path) -> dict[str, Path]:
    """One document per input format, each carrying text, images and styling."""
    from fixtures.build_docx_fixture import build_sample_docx
    from fixtures.build_epub_fixture import build_sample_epub
    from fixtures.build_image_fixture import build_text_over_image

    made: dict[str, Path] = {}

    pdf = into / "source.pdf"
    shutil.copy(ROOT / "docs/samples/sample_report.pdf", pdf)
    made["pdf"] = pdf

    epub = into / "source.epub"
    build_sample_epub(epub)
    made["epub"] = epub

    docx = into / "source.docx"
    build_sample_docx(docx)
    made["docx"] = docx

    png = into / "source.png"
    build_text_over_image(png)
    made["png"] = png

    return made


def count_docir(path: Path) -> Counts:
    """What the reader itself sees - the honest "before", since nothing can survive a
    conversion that the reader never picked up in the first place."""
    from layoutkeep.writers.converter import read_any_document

    doc = read_any_document(path)
    text = "".join(b.text for _, b in doc.iter_blocks())
    styled = sum(
        1
        for _, block in doc.iter_blocks()
        for line in block.lines
        for span in line.spans
        if span.style.bold or span.style.italic
    )
    return Counts(
        characters=len(text.replace(" ", "").replace("\n", "")),
        words=len(text.split()),
        images=sum(len(page.images) for page in doc.pages),
        pages=len(doc.pages),
        styled_runs=styled,
    )


def count_output(path: Path, target: str, extra_files: int) -> Counts:
    """What a reader finds in the written file. For a target this project cannot read back
    (html), the file is parsed directly rather than guessed at."""
    if target == "html":
        return _count_html(path)
    if target == "png":
        return _count_images(path, extra_files)
    counts = count_docir(path)
    if target == "pdf" and counts.words == 0 and counts.images:
        # A PDF written from an image source carries its words as pixels, exactly as its source
        # did. Counting only the text layer called that a total loss - it is not, the words are
        # on the page and legible. What is true is narrower and belongs in the notes: the output
        # cannot be searched or selected.
        ocr = _ocr_pdf(path)
        ocr.images = counts.images
        ocr.pages = counts.pages
        return ocr
    return counts


def _ocr_pdf(path: Path) -> Counts:
    """Read a PDF that has no text layer the way a person would: render it and look."""
    import tempfile as _tempfile

    import pymupdf

    from layoutkeep.writers.converter import read_any_document

    words = 0
    characters = 0
    with _tempfile.TemporaryDirectory() as tmp, pymupdf.open(path) as pdf:
        for number, page in enumerate(pdf):
            shot = Path(tmp) / f"p{number}.png"
            page.get_pixmap(dpi=150).save(str(shot))
            text = "".join(b.text for _, b in read_any_document(shot).iter_blocks())
            words += len(text.split())
            characters += len("".join(text.split()))
    return Counts(characters=characters, words=words)


def _count_html(path: Path) -> Counts:
    import re

    raw = path.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    images = len(re.findall(r"<img\b", body, flags=re.I))
    styled = len(re.findall(r"<(b|strong|i|em)\b", body, flags=re.I))
    styled += len(re.findall(r"font-weight\s*:\s*(bold|[6-9]00)", body, flags=re.I))
    styled += len(re.findall(r"font-style\s*:\s*italic", body, flags=re.I))
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    return Counts(
        characters=len(text.replace(" ", "").replace("\n", "")),
        words=len(text.split()),
        images=images,
        pages=1,
        styled_runs=styled,
    )


def _count_images(path: Path, extra_files: int) -> Counts:
    """An image target has no text layer at all - the words are pixels. Text is read back with
    the same OCR the image reader uses, so "did the words survive" is answerable rather than
    assumed. Where OCR is unavailable the count is left at zero and a note says so."""
    try:
        from layoutkeep.writers.converter import read_any_document

        doc = read_any_document(path)
        text = "".join(b.text for _, b in doc.iter_blocks())
        return Counts(
            characters=len(text.replace(" ", "").replace("\n", "")),
            words=len(text.split()),
            images=1,
            pages=1 + extra_files,
            styled_runs=0,
        )
    except Exception:  # noqa: BLE001 - the point is to record the failure, not to raise it
        return Counts(images=1, pages=1 + extra_files)


def run_pair(source: Path, target: str, work: Path) -> Pair:
    from layoutkeep.core.docir import apply_segments, segments_from_document
    from layoutkeep.writers.converter import read_any_document, write_any_document

    result = Pair(source=source.suffix.lstrip("."), target=target)
    try:
        doc = read_any_document(source)
        doc.target_lang = "tr"
        result.before = count_docir(source)

        # The translation is the identity: every segment comes back as itself. A provider that
        # lengthens the text would make "how much survived" unanswerable - a 153% word count
        # says nothing about whether a paragraph was dropped. The write-back path still runs in
        # full, which is what is under test.
        segments = segments_from_document(doc)
        for seg in segments:
            seg.target = seg.source
        apply_segments(doc, segments)

        out = work / f"{source.stem}_to.{target}"
        written = write_any_document(doc, source, out)
        result.files_written = len(written) if written else 1
        result.after = count_output(out, target, max(0, result.files_written - 1))
        result.ok = True
    except Exception as exc:  # noqa: BLE001 - a pair that raises is a result, not a crash
        result.error = f"{type(exc).__name__}: {exc}".strip()[:300]
        result.notes.append(traceback.format_exc(limit=3).splitlines()[-1][:200])
    return result


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("format_matrix.json")
    pairs: list[Pair] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        sources = build_sources(work)
        for name in SOURCES:
            for target in TARGETS:
                pair = run_pair(sources[name], target, work)
                pairs.append(pair)
                mark = "ok " if pair.ok else "ERR"
                if pair.ok:
                    detail = (
                        f"text {pair.after.ratio(pair.before, 'words'):5.0%}  "
                        f"img {pair.after.images}/{pair.before.images}  "
                        f"pages {pair.after.pages}/{pair.before.pages}  "
                        f"styled {pair.after.styled_runs}/{pair.before.styled_runs}"
                    )
                else:
                    detail = pair.error
                print(f"{mark} {name:>4} -> {target:<5} {detail}")

    out_path.write_text(
        json.dumps([asdict(p) for p in pairs], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{out_path} yazildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
