"""Render real before/after pages for a handful of open pairs, for a side-by-side visual
comparison artifact - not a word-count table, actual rendered output from the real pipeline.

Runs the identity translation (no live LLM provider in this environment) through the real
reader and writer for each pair, then rasterizes both sides to PNG so they can be embedded
directly in an HTML page.

    .venv/Scripts/python.exe tools/audit/render_real_comparison.py
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pymupdf  # noqa: E402

from layoutkeep.core.docir import apply_segments, segments_from_document  # noqa: E402
from layoutkeep.writers.converter import read_any_document, write_any_document  # noqa: E402

OUT_DIR = ROOT / "_artifacts" / "output" / "real-comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAIRS = [
    ("rich_report.docx", "pdf", "docx_to_pdf"),
    ("rich_book.epub", "docx", "epub_to_docx"),
    ("rich_report.pdf", "html", "pdf_to_html"),
    ("rich_report.docx", "png", "docx_to_png"),
]


def _rasterize_native(path: Path, dest: Path) -> None:
    """Render a file with MuPDF's own reader for that format - PDF, DOCX and EPUB all have
    native support - so the "before" image is the file as any ordinary viewer shows it,
    completely independent of LayoutKeep's own reader/writer under test."""
    with pymupdf.open(path) as doc:
        doc[0].get_pixmap(dpi=150).save(str(dest))


def _run_identity(source: Path, target_ext: str, out: Path) -> list[Path]:
    doc = read_any_document(source)
    doc.target_lang = "tr"
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = seg.source
    apply_segments(doc, segments)
    return write_any_document(doc, source, out)


def main() -> None:
    manifest: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for source_name, target_ext, label in PAIRS:
            source = ROOT / "tests" / "fixtures" / source_name
            entry: dict = {"label": label, "source": source_name, "target": target_ext}

            # --- left side: the original file, rendered by MuPDF's own reader for its
            # format - not LayoutKeep's code, so this is what any ordinary viewer shows. ---
            left = OUT_DIR / f"{label}_source.png"
            _rasterize_native(source, left)
            entry["source_image"] = left.name

            # --- right side: the real output of the pair under test ---
            out = work / f"{label}_out.{target_ext}"
            written = _run_identity(source, target_ext, out)
            out_path = (written or [out])[0]

            if target_ext == "png":
                right = OUT_DIR / f"{label}_target.png"
                right.write_bytes(out_path.read_bytes())
                entry["target_image"] = right.name
            elif target_ext == "html":
                right = OUT_DIR / f"{label}_target.html"
                right.write_bytes(out_path.read_bytes())
                entry["target_html"] = right.name
            elif target_ext == "docx":
                # MuPDF's native .docx renderer does not draw embedded images at all - checked
                # directly against the zip (word/media/image1.png is there, one <a:blip>
                # reference to it) - so it would show a DOCX with a real image as if the image
                # were missing. Re-read the file with LayoutKeep's own docx_reader (already
                # confirmed faithful to the zip contents) and view it through the PDF path
                # instead, which MuPDF renders correctly.
                right = OUT_DIR / f"{label}_target.png"
                view_pdf = work / f"{label}_view.pdf"
                _run_identity(out_path, "pdf", view_pdf)
                _rasterize_native(view_pdf, right)
                entry["target_image"] = right.name
                entry["target_note"] = "MuPDF görüntüleyicisi .docx'teki gömülü görseli göstermediği için LayoutKeep'in kendi okuyucusuyla görüntülendi"
            else:
                right = OUT_DIR / f"{label}_target.png"
                _rasterize_native(out_path, right)
                entry["target_image"] = right.name

            manifest.append(entry)
            print(f"ok   {label}: {entry}")

    import json
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
