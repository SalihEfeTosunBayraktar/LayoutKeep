"""A link's underline goes with the words it underlined.

WHY THIS EXISTS: a Wikipedia page draws every link's underline as a thin filled rectangle along the
bottom of the link. The writer removes the translated words and draws new ones, but left the line
art alone, so the old underlines stayed where the English words had been and ran through the
Turkish text like strike-throughs (every page of the 0.9.10 bench's wiki documents).

Only line art that is an underline goes: thin, along the bottom edge of a link, inside a block whose
text changed. A rule, a fraction bar or a table border is not a link's underline and stays.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import write_pdf

TEXT = "Photosynthesis is a system of biological processes by which organisms convert light."


def _source(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 80), TEXT, fontsize=10)
    words = {w[4]: pymupdf.Rect(w[:4]) for w in page.get_text("words")}
    link = words["biological"] | words["processes"]
    # The underline, as a browser prints it: a filled rectangle under the link's words.
    page.draw_rect(pymupdf.Rect(link.x0, link.y1 - 0.75, link.x1, link.y1), color=None, fill=(0.6, 0.6, 0.6))
    page.insert_link({"kind": pymupdf.LINK_URI, "from": link, "uri": "https://example.org"})
    # A rule under the paragraph, not a link's: it must survive.
    page.draw_rect(pymupdf.Rect(40, 120, 360, 120.75), color=None, fill=(0, 0, 0))
    doc.save(path)
    return path


def _thin_fills(path: Path) -> list[pymupdf.Rect]:
    with pymupdf.open(path) as doc:
        return [d["rect"] for d in doc[0].get_drawings() if d["rect"].height < 1.5]


def test_a_translated_links_underline_is_removed_and_a_rule_is_kept(tmp_path: Path) -> None:
    src = _source(tmp_path / "src.pdf")
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for segment in segments:
        segment.target = "Fotosentez, organizmaların ışığı dönüştürdüğü biyolojik süreçler sistemidir."
    apply_segments(doc, segments)
    out = tmp_path / "out.pdf"

    write_pdf(doc, src, out)

    left = _thin_fills(out)
    assert len(left) == 1 and left[0].y0 >= 119, f"underline left behind, or rule lost: {left}"


def test_an_untranslated_links_underline_stays(tmp_path: Path) -> None:
    src = _source(tmp_path / "src.pdf")
    doc = read_pdf(src)
    out = tmp_path / "out.pdf"

    write_pdf(doc, src, out)

    assert len(_thin_fills(out)) == 2
