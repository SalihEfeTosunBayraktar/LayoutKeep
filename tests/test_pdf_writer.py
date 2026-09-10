"""Unit tests for pdf_writer.write_pdf against the fixture PDFs."""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_pdf_fixture import (
    build_background_art,
    build_bold_italic,
    build_rotated_spaced_line,
    build_rotated_text,
    build_running_header_footer,
    build_two_column,
)

from layoutkeep.core.docir import BBox, Style, apply_segments, segments_from_document
from layoutkeep.fitting import fit_segment
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.writers.pdf_writer import measure_fit, write_pdf


def _translate_all(doc, transform) -> None:
    segments = segments_from_document(doc)
    for seg in segments:
        seg.target = transform(seg.source)
    apply_segments(doc, segments)


def test_page_number_and_header_survive_untouched(tmp_path: Path) -> None:
    src = tmp_path / "hf.pdf"
    build_running_header_footer(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: f"XX {s}")

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        for i, page in enumerate(result, start=1):
            # normalize the "fi" ligature insert_htmlbox may substitute when re-rendering
            text = page.get_text().replace("ﬁ", "fi")
            assert f"\n{i}\n" in text or text.strip().startswith(str(i))
            assert "XX Running Header Text" in text
            assert "XX Confidential Draft" in text


def test_two_column_translation_stays_in_its_own_column(tmp_path: Path) -> None:
    src = tmp_path / "two_col.pdf"
    build_two_column(src)
    doc = read_pdf(src)
    _translate_all(doc, str.upper)

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        text = result[0].get_text()
    assert "LEFT COLUMN" in text
    assert "RIGHT COLUMN" in text


def test_background_art_survives_redaction(tmp_path: Path) -> None:
    src = tmp_path / "bg.pdf"
    build_background_art(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: f"Translated: {s}")

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        page = result[0]
        assert len(page.get_image_info()) == 1
        assert len(page.get_drawings()) == 1
        assert "Translated:" in page.get_text()


def test_bold_italic_roundtrip_after_translation(tmp_path: Path) -> None:
    src = tmp_path / "bi.pdf"
    build_bold_italic(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: s.replace("word", "WORT"))

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        spans = [
            s
            for b in result[0].get_text("dict")["blocks"]
            for line in b["lines"]
            for s in line["spans"]
        ]
    bold_flag = 1 << 4
    italic_flag = 1 << 1
    bold_spans = [s for s in spans if s["flags"] & bold_flag]
    italic_spans = [s for s in spans if s["flags"] & italic_flag]
    assert any("bold" in s["text"] for s in bold_spans)
    assert any("italic" in s["text"] for s in italic_spans)


def test_measure_fit_reports_overflow() -> None:
    style = Style(font_family="Helvetica", size=12.0)
    tiny_box = BBox(0, 0, 20, 12)
    fits, _scale = measure_fit("A very long sentence that cannot fit in a tiny box.", style, tiny_box)
    assert fits is False


def test_measure_fit_reports_fit() -> None:
    style = Style(font_family="Helvetica", size=10.0)
    big_box = BBox(0, 0, 400, 200)
    fits, scale = measure_fit("Short text.", style, big_box)
    assert fits is True
    assert 0 < scale <= 1


def test_rotated_text_survives_translation_at_the_same_angle(tmp_path: Path) -> None:
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: f"XX {s}")

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    result = read_pdf(out)
    by_text = {b.text: b for b in result.pages[0].blocks}
    assert "XX Noob" in by_text
    assert by_text["XX Noob"].rotation == pytest.approx(-18.8, abs=1.0)
    assert "XX Sideways" in by_text
    assert by_text["XX Sideways"].rotation == pytest.approx(-90.0, abs=1.0)
    assert "XX Upside Down" in by_text
    assert abs(by_text["XX Upside Down"].rotation) == pytest.approx(180.0, abs=1.0)


def test_fit_segment_through_real_measure_fit_produces_output(tmp_path: Path) -> None:
    """End-to-end regression for the `fit.fit_segment` -> `pdf_writer.measure_fit` seam.

    This is the gap that let a signature break on that seam through 387 green tests: the
    fitting-layer tests exercise `fit_segment` against fake `measure` callbacks that were
    updated alongside any signature change, so nothing here ever called the *real*
    `measure_fit`. This test wires `fit_segment` to the real `measure_fit` - the same call
    `cli.py`'s `_fit_pdf` makes - on a PDF with a rotated block, so a keyword mismatch between
    `fit.py` and `pdf_writer.py` fails a test instead of only failing in production.
    """
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    blocks = {b.id: b for _, b in doc.iter_blocks()}
    for seg in segments:
        seg.target = f"XX {seg.source}"
        block = blocks[seg.block_id]
        result = fit_segment(
            seg, block.dominant_style(), block.bbox, measure_fit, rotation=block.rotation
        )
        seg.target = result.text
    apply_segments(doc, segments)

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    assert out.exists()
    with pymupdf.open(out) as result:
        text = result[0].get_text()
    assert "XX Noob" in text or "Noob" in text  # rotated block survived the round trip


def test_rotated_redaction_does_not_erase_neighbouring_text(tmp_path: Path) -> None:
    """A rotated line's axis-aligned bbox is bigger than its glyphs. If redaction used that bbox
    directly here, the nearby control paragraph (which sits inside the "Noob" label's bbox
    height range) would be damaged too."""
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: f"XX {s}")

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    result = read_pdf(out)
    texts = [b.text for b in result.pages[0].blocks]
    assert any("Ordinary horizontal" in t for t in texts)
    assert any(t == "XX Noob" for t in texts)


def test_a_spaced_rotated_line_is_erased_all_the_way(tmp_path: Path) -> None:
    """`search_for` reports a letter-spaced rotated line as several consecutive quads. Redacting
    only the first one left the tail of the source text on the page, and the translation was
    then drawn over it - two strings on top of each other, both legible, seen on a real file."""
    src = tmp_path / "spaced.pdf"
    build_rotated_spaced_line(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: "GOSTERI ZAMANI")

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        text = result[0].get_text().replace(" ", "")
    assert "GOSTERIZAMANI" in text
    # Nothing of the English line may survive underneath it.
    assert "show" not in text.lower()
    assert "time" not in text.lower()


def test_the_writer_keeps_text_readable_until_that_would_lose_it(tmp_path: Path) -> None:
    """The writer may not shrink past the readability floor `fitting/` works to - a 7pt footer
    came back at 3.9pt on a real document, under a review flag fitting had already raised.

    But `insert_htmlbox` draws *nothing* when it cannot fit at the floor, so a translation long
    enough to miss it must still reach the page at whatever size it takes.
    """
    src = tmp_path / "cols.pdf"
    build_two_column(src)
    doc = read_pdf(src)
    _translate_all(doc, lambda s: s + " " + "uzatma " * 40)

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    with pymupdf.open(out) as result:
        text = " ".join(page.get_text() for page in result)
    assert "uzatma" in text


def test_a_translation_that_fits_is_not_shrunk_below_the_floor(tmp_path: Path) -> None:
    """Same-length text has no reason to lose points off its size."""
    src = tmp_path / "cols.pdf"
    build_two_column(src)
    doc = read_pdf(src)
    sizes_before = {b.id: b.dominant_style().size for p in doc.pages for b in p.blocks}
    _translate_all(doc, lambda s: s)

    out = tmp_path / "out.pdf"
    write_pdf(doc, src, out)

    result = read_pdf(out)
    for page in result.pages:
        for block in page.blocks:
            before = sizes_before.get(block.id)
            if before:
                assert block.dominant_style().size >= before * 0.85 - 0.1


BUNDLED_FAMILIES = ["Tinos", "Arimo", "Cousine", "Caladea", "Carlito"]


@pytest.mark.parametrize("family", BUNDLED_FAMILIES)
@pytest.mark.parametrize(("bold", "italic"), [(False, False), (False, True), (True, False), (True, True)])
def test_every_bundled_family_can_deliver_every_style(family: str, bold: bool, italic: bool) -> None:
    """A resolved font must actually carry the weight and slant it was resolved for.

    `_matches_requested_style` rejects a font that does not, and a rejected font drops the block
    back to the generic base-14 mapping - losing the metric compatibility the bundle exists for.
    That rejection is silent, so it went unnoticed that three families shipped no bold-italic
    face at all: Cousine, Caladea and Carlito each fell back to their upright italic, failed the
    guard, and quietly lost their metrics wherever a document used bold italic.
    """
    from layoutkeep.fitting.fontmatch import FontRegistry
    from layoutkeep.writers.pdf_writer import _matches_requested_style, _subset_font

    resolved = FontRegistry().find_family(family, bold=bold, italic=italic)
    assert resolved is not None, f"{family} b={bold} i={italic} resolved to nothing"

    subset = _subset_font((resolved.path, resolved.font_number), "AaBb 0123", bold=bold)
    assert _matches_requested_style(subset, bold=bold, italic=italic), (
        f"{family} b={bold} i={italic} resolved to {resolved.path} which does not carry that "
        "style, so pdf_writer would silently fall back to base-14"
    )


def test_a_short_label_is_not_shrunk_by_the_renderers_own_padding(tmp_path: Path) -> None:
    """The reader measures the tight glyph box; `insert_htmlbox` wants more than that for its
    own inset. On a paragraph that costs nothing, on a 6pt chart tick it is most of the width -
    "0.6" came back at 4.4pt on a real document, and nothing had even translated it."""
    import pymupdf as fitz

    src = tmp_path / "ticks.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    writer = fitz.TextWriter(page.rect)
    writer.append((40, 60), "0.6", fontsize=6)
    writer.write_text(page)
    doc.save(str(src))
    doc.close()

    read = read_pdf(src)
    _translate_all(read, lambda s: s)  # untouched text: nothing here justifies any shrinking

    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)

    with pymupdf.open(out) as result:
        sizes = [
            span["size"]
            for block in result[0].get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
        ]
    assert sizes, "the label must still be on the page"
    assert min(sizes) >= 5.7, f"6pt label rendered at {min(sizes):.2f}pt"


def test_a_ligature_does_not_corrupt_the_text_layer(tmp_path: Path) -> None:
    """Subsetting renumbers glyphs and the ligature's route back to Unicode does not survive it:
    "İstifleme" drew correctly and copied out of the finished PDF as "İsti{eme". Unsubsetted it
    copies as U+FB02, which no search for "fl" matches either. Both are useless in a document
    someone has to search, quote or feed to another tool."""
    src = tmp_path / "lig.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=120)
    page.insert_textbox(pymupdf.Rect(20, 20, 280, 60), "Stacking order", fontsize=10)
    doc.save(str(src))
    doc.close()

    read = read_pdf(src)
    read.target_lang = "tr"
    _translate_all(read, lambda s: "İstifleme sırası")

    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)

    with pymupdf.open(out) as result:
        text = result[0].get_text()
    assert "İstifleme" in text, f"text layer reads {text.strip()!r}"
    assert "\ufb02" not in text
