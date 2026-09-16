"""A block whose translation is its source is left exactly as it was set.

Digital pilot 2: the running header "NIST SP 800-12 REV. 1" is set in small caps (three spans, two
sizes). It rightly comes back unchanged - it is a document code - yet the writer removed the
original glyphs and redrew the text in a substitute font, wider than the original, so it was
shrunk below the readability floor on every page. Names, codes and headers that do not change
lose nothing by being left alone, and lose their typography by being redrawn.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf


def _page(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 40), "NIST SP 800-12 REV. 1", fontname="tiro", fontsize=9)
    page.insert_text((40, 150), "Information security protects information and systems.", fontname="helv", fontsize=11)
    doc.save(str(path))


def test_an_unchanged_block_keeps_its_original_glyphs(tmp_path: Path) -> None:
    src = tmp_path / "hdr.pdf"
    _page(src)
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = seg.source if "NIST" in seg.source else "Bilgi guvenligi bilgiyi ve sistemleri korur."
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        spans = [s for b in result[0].get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for s in ln["spans"]]
    header = [s for s in spans if "NIST" in s["text"]]
    assert header, "the header disappeared"
    assert all(s["font"].startswith("Times") for s in header), [s["font"] for s in header]
    assert all(abs(s["size"] - 9) < 0.01 for s in header), [s["size"] for s in header]
