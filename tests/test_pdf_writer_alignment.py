"""A centred block is drawn centred.

NASA report cover, translated: the reader marked the title lines `align=center` correctly, and
every one of them came out hard against the left edge of its box. `pdf_writer` never read
`Block.align` - the HTML and DOCX writers do, this one did not - so a block's box was the width
of its longest line and every shorter line started at the box's left edge.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf

_WIDTH = 612.0


def _centred_title(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=_WIDTH, height=792)
    for top, text in ((150, "NATIONAL ADVISORY COMMITTEE FOR"), (172, "AERONAUTICS")):
        length = pymupdf.get_text_length(text, fontname="helv", fontsize=16)
        page.insert_text(((_WIDTH - length) / 2, top), text, fontname="helv", fontsize=16)
    page.insert_text((72, 400), "Body text that is set flush left on the page as usual.", fontsize=11)
    doc.save(str(path))


def test_a_centred_title_is_drawn_centred(tmp_path: Path) -> None:
    src = tmp_path / "cover.pdf"
    _centred_title(src)
    doc = read_pdf(src)
    title = next(b for _p, b in doc.iter_blocks() if "AERONAUTICS" in b.text)
    assert title.align == "center", title.align

    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = seg.source.replace("AERONAUTICS", "HAVACILIK")
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        words = [w for w in result[0].get_text("words") if w[4] == "HAVACILIK"]
    assert words, "translated line not found"
    x0, _y0, x1, *_ = words[0]
    assert abs((x0 + x1) / 2 - _WIDTH / 2) < 12, f"line centre {(x0 + x1) / 2:.0f}, page centre {_WIDTH / 2:.0f}"
