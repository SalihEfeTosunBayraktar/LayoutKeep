"""Builds small, reproducible PDFs used by the pdf reader/writer tests.

Built with pymupdf itself (the only place besides `readers/pdf_reader.py` and
`writers/pdf_writer.py` that this project imports it), so the fixtures need no external files
and carry no third-party content.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 400.0, 500.0


def _header_footer(page: pymupdf.Page, title: str, page_no: int) -> None:
    page.insert_text((20, 20), title, fontsize=8, fontname="helv")
    page.insert_text((PAGE_W / 2 - 5, PAGE_H - 15), str(page_no), fontsize=8, fontname="helv")


def build_single_column(path: str | Path) -> None:
    """One page: header, one body paragraph, footer page number."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _header_footer(page, "Sample Report", 1)
    page.insert_textbox(
        pymupdf.Rect(40, 60, 360, 200),
        "This is a single column body paragraph used to check plain reading order "
        "and paragraph merging across several wrapped lines of body text.",
        fontsize=11,
        fontname="helv",
    )
    doc.save(str(path))
    doc.close()


def build_two_column(path: str | Path) -> None:
    """One page: header, page number footer, two body columns that must not interleave."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _header_footer(page, "Two Column Report", 1)
    page.insert_textbox(
        pymupdf.Rect(30, 60, 190, 400),
        "Left column first sentence. Left column second sentence. Left column third "
        "sentence continues the same paragraph to the bottom of the column.",
        fontsize=10,
        fontname="helv",
    )
    page.insert_textbox(
        pymupdf.Rect(210, 60, 370, 400),
        "Right column first sentence. Right column second sentence. Right column "
        "third sentence continues the same paragraph to the bottom of the column.",
        fontsize=10,
        fontname="helv",
    )
    doc.save(str(path))
    doc.close()


def build_split_heading(path: str | Path) -> None:
    """One page: a two-line heading placed with wide leading so PyMuPDF returns each line as its
    own text block, plus unrelated scattered body words - reproduces a real user PDF where the
    reader's paragraph merging must join same-size, vertically adjacent, x-overlapping lines that
    the text-extraction layer did not group on its own."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((60, 90), "Hello How Are", fontsize=24, fontname="helv")
    page.insert_text((70, 125), "You Today?", fontsize=24, fontname="helv")
    page.insert_text((30, 250), "Scattered", fontsize=11, fontname="helv")
    page.insert_text((300, 400), "Words", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def build_scattered_no_columns(path: str | Path) -> None:
    """One page: three unrelated blocks placed diagonally, each at a different x, with
    non-overlapping vertical extents. `_cluster_columns` still splits these into x-bands - there
    is nothing to stop it - but the bands never coexist at the same height, so this is not a real
    multi-column layout and reading order must fall back to plain top-to-bottom."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((280, 150), "Top block", fontsize=11, fontname="helv")
    page.insert_text((40, 250), "Middle block", fontsize=11, fontname="helv")
    page.insert_text((330, 350), "Bottom block", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def build_running_header_footer(path: str | Path) -> None:
    """Three pages sharing the same header text and footer text, only the page number differs."""
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_text((20, 20), "Running Header Text", fontsize=8, fontname="helv")
        page.insert_text((20, PAGE_H - 35), "Confidential Draft", fontsize=8, fontname="helv")
        page.insert_text((PAGE_W / 2 - 5, PAGE_H - 10), str(i), fontsize=8, fontname="helv")
        page.insert_textbox(
            pymupdf.Rect(40, 60, 360, 200),
            f"Body paragraph unique to page {i}, so only the header and footer repeat.",
            fontsize=11,
            fontname="helv",
        )
    doc.save(str(path))
    doc.close()


def build_hyphenated(path: str | Path) -> None:
    """One page: a paragraph with a hyphenated line break that must be rejoined."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_textbox(
        pymupdf.Rect(40, 60, 220, 200),
        "This demonstrates hyphen-\nation across a line break.",
        fontsize=11,
        fontname="helv",
    )
    doc.save(str(path))
    doc.close()


def build_bold_italic(path: str | Path) -> None:
    """One page: a paragraph with inline bold and italic runs, same line."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((40, 80), "This word is ", fontsize=12, fontname="helv")
    x = 40 + pymupdf.get_text_length("This word is ", fontname="helv", fontsize=12)
    page.insert_text((x, 80), "bold", fontsize=12, fontname="hebo")
    x += pymupdf.get_text_length("bold", fontname="hebo", fontsize=12)
    page.insert_text((x, 80), " and this is ", fontsize=12, fontname="helv")
    x += pymupdf.get_text_length(" and this is ", fontname="helv", fontsize=12)
    page.insert_text((x, 80), "italic", fontsize=12, fontname="heit")
    doc.save(str(path))
    doc.close()


def build_background_art(path: str | Path) -> None:
    """One page: a filled vector rectangle and a raster image under a text paragraph."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.draw_rect(
        pymupdf.Rect(20, 20, PAGE_W - 20, PAGE_H - 20),
        color=(0, 0, 0.6),
        fill=(0.85, 0.9, 1.0),
        width=2,
    )
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.set_rect(pix.irect, (255, 210, 120))
    page.insert_image(pymupdf.Rect(40, 40, 100, 100), pixmap=pix)
    page.insert_textbox(
        pymupdf.Rect(40, 120, 360, 220),
        "Body text drawn on top of a background rectangle and a small raster image, "
        "used to check that redaction does not erase the art underneath.",
        fontsize=11,
        fontname="helv",
    )
    doc.save(str(path))
    doc.close()


def build_rotated_text(path: str | Path) -> None:
    """One page: horizontal body text plus three rotated labels - a shallow diagonal angle (the
    common case: a watermark or a tilted stamp), an exact 90 and an exact 180 - since the shallow
    and right-angle cases go through different code paths and fail differently."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_textbox(
        pymupdf.Rect(30, 30, 370, 70),
        "Ordinary horizontal body text, unrotated, used as a control block.",
        fontsize=11,
        fontname="helv",
    )
    # Shallow angle: pymupdf's simple insert_text only rotates in quadrants, so an arbitrary
    # angle needs the TextWriter + morph route - the same one the writer uses to draw it back.
    tw = pymupdf.TextWriter(page.rect)
    tw.append((60, 250), "Noob", fontsize=24)
    tw.write_text(page, morph=(pymupdf.Point(60, 250), pymupdf.Matrix(1, 1).prerotate(18.8)))
    page.insert_text((300, 150), "Sideways", fontsize=14, fontname="helv", rotate=90)
    page.insert_text((350, 400), "Upside Down", fontsize=14, fontname="helv", rotate=180)
    doc.save(str(path))
    doc.close()


def build_mirrored_text(path: str | Path) -> None:
    """One page: a normal control line and a horizontally-mirrored line (negative-determinant
    transform, `Matrix(-1, 1)` - text flipped left-right, glyphs backwards) placed so that its
    reported flow direction lands on the same angle as an ordinary 180-degree rotation.

    This reproduces the ambiguity investigated for the mirrored-text task: pymupdf's
    `get_text()` family (dict/rawdict/rawjson/words/texttrace) reports only a line's flow
    direction vector (`dir`) and axis-aligned boxes, never the sign of the underlying glyph
    transform's determinant. A mirrored line and a genuinely-rotated line can produce the exact
    same `dir`, so `rotation` alone cannot and must not be read as "this line is also unmirrored".
    See the note on `_block_rotation` in `readers/pdf_reader.py`.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_textbox(
        pymupdf.Rect(30, 30, 370, 70),
        "Ordinary horizontal control text, not mirrored.",
        fontsize=11,
        fontname="helv",
    )
    font = pymupdf.Font(fontname="helv")
    tw = pymupdf.TextWriter(page.rect)
    tw.append((200, 250), "Mirrored Label", font=font, fontsize=20)
    # Matrix(-1, 1) has determinant -1: a horizontal flip, not a rotation. The morph anchor must
    # match the append point or the flip also translates the text off its intended position.
    tw.write_text(page, morph=(pymupdf.Point(200, 250), pymupdf.Matrix(-1, 1)))
    doc.save(str(path))
    doc.close()


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    build_single_column(out_dir / "pdf_single_column.pdf")
    build_two_column(out_dir / "pdf_two_column.pdf")
    build_split_heading(out_dir / "pdf_split_heading.pdf")
    build_scattered_no_columns(out_dir / "pdf_scattered_no_columns.pdf")
    build_running_header_footer(out_dir / "pdf_running_header_footer.pdf")
    build_hyphenated(out_dir / "pdf_hyphenated.pdf")
    build_bold_italic(out_dir / "pdf_bold_italic.pdf")
    build_background_art(out_dir / "pdf_background_art.pdf")
    build_rotated_text(out_dir / "pdf_rotated_text.pdf")
    build_mirrored_text(out_dir / "pdf_mirrored_text.pdf")


def build_rotated_spaced_line(path: str | Path) -> None:
    """One page: a long rotated line whose glyphs are spaced far apart.

    Letter-spacing is what breaks redaction. `search_for` reports a hit like this as several
    consecutive quads rather than one, because the gaps between glyphs read as breaks - so a
    redaction that only takes the first quad erases the beginning of the line and leaves the
    rest of the source text on the page, underneath the translation.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    writer = pymupdf.TextWriter(page.rect)
    # The private-use character is the trigger: `search_for` cannot match a glyph that has no
    # Unicode meaning, so the hit comes back as the fragments on either side of it. Real
    # documents produce these whenever a symbol-encoded font is used for an apostrophe.
    writer.append((60, 300), "i t  s   s h o w   t i m e", fontsize=14)
    writer.write_text(page, morph=(pymupdf.Point(60, 300), pymupdf.Matrix(1, 1).prerotate(17.5)))
    doc.save(str(path))
    doc.close()
