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


def test_an_unchanged_block_overlapped_by_a_translated_one_is_not_lost(tmp_path: Path) -> None:
    """NIST campaign run: URLs that came back unchanged were left in place - and then erased by
    the redaction of the translated paragraph whose box they sit against ("https://doi.org/..."
    gone from the page). A kept block the redaction would reach is redrawn like any other."""
    src = tmp_path / "url.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 100), "This publication is available free of charge from:", fontsize=11)
    page.insert_text((40, 140), "https://doi.org/10.6028/NIST.SP.800-12r1", fontsize=11)
    doc.save(str(src))

    read = read_pdf(src)
    blocks = [b for _p, b in read.iter_blocks()]
    assert len(blocks) == 2, [b.text for b in blocks]
    url = next(b for b in blocks if "doi.org" in b.text)
    # As on the real page (NIST p3: paragraph 328-341, URL 338-351): the paragraph's box reaches a
    # few points into the URL line beneath it.
    for block in blocks:
        if "available" in block.text:
            block.bbox.y1 = url.bbox.y0 + 3.0
    segments = segments_from_document(read)
    for seg in segments:
        seg.target = seg.source if "doi.org" in seg.source else "Bu yayin ucretsiz olarak su adresten edinilebilir:"
    apply_segments(read, segments)
    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)
    with pymupdf.open(out) as result:
        assert "doi.org" in result[0].get_text()


def test_a_kept_block_reached_through_another_kept_block_is_not_lost(tmp_path: Path) -> None:
    """NIST references page: a translated entry reached the unchanged line "128 Stat. 3073.
    http://www.gpo.gov/fdsys/pkg/PLAW-" beneath it, which was therefore redrawn - and that line's
    own clearing reached the next unchanged line, "113publ283/pdf/PLAW-113publ283.pdf", which
    nothing had marked. Every block a clearing reaches is redrawn, however many steps away."""
    src = tmp_path / "chain.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((40, 100), "Federal Information Security Modernization Act of 2014", fontsize=11)
    page.insert_text((40, 140), "128 Stat. 3073. http://www.gpo.gov/fdsys/pkg/PLAW-", fontsize=11)
    page.insert_text((40, 180), "113publ283/pdf/PLAW-113publ283.pdf", fontsize=11)
    doc.save(str(src))

    read = read_pdf(src)
    blocks = sorted((b for _p, b in read.iter_blocks()), key=lambda b: b.bbox.y0)
    assert len(blocks) == 3, [b.text for b in blocks]
    # As measured on the page: each box reaches a couple of points into the one below it.
    blocks[0].bbox.y1 = blocks[1].bbox.y0 + 2.0
    blocks[1].bbox.y1 = blocks[2].bbox.y0 + 2.0
    segments = segments_from_document(read)
    for seg in segments:
        seg.target = "2014 Federal Bilgi Guvenligi Modernizasyonu Yasasi" if "Modernization" in seg.source else seg.source
    apply_segments(read, segments)
    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)
    with pymupdf.open(out) as result:
        assert "113publ283" in result[0].get_text()
