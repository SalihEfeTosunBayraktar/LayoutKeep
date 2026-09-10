"""Unit tests for pdf_reader.read_pdf against the fixture PDFs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_pdf_fixture import (
    build_background_art,
    build_bold_italic,
    build_hyphenated,
    build_mirrored_text,
    build_rotated_text,
    build_running_header_footer,
    build_scattered_no_columns,
    build_single_column,
    build_split_heading,
    build_two_column,
)

from layoutkeep.core.docir import BBox, BlockRole, Line, Span, Style
from layoutkeep.readers.pdf_reader import _infer_alignment, _looks_like_math, read_pdf

# -- S6: mathematics blocks must be classified FORMULA, not BODY -------------------------


def test_alignment_centered_block() -> None:
    # 600pt page, block centred around x=300 with balanced margins.
    assert _infer_alignment(BBox(150, 0, 450, 20), 600) == "center"


def test_alignment_right_block() -> None:
    # Block hugged to the right edge (right margin < 5%, left margin > 15%).
    assert _infer_alignment(BBox(480, 0, 590, 20), 600) == "right"


def test_alignment_left_block() -> None:
    assert _infer_alignment(BBox(50, 0, 200, 20), 600) == "left"


def test_alignment_full_width_stays_left() -> None:
    # A justified paragraph spanning nearly the whole page must not be read as centred.
    assert _infer_alignment(BBox(30, 0, 570, 20), 600) == "left"


def _line_with_font(font: str, text: str = "x") -> Line:
    return Line(
        spans=[Span(text=text, bbox=BBox(0, 0, 10, 10), style=Style(font_family=font))],
        bbox=BBox(0, 0, 10, 10),
    )


def test_latex_math_fonts_classified_as_math() -> None:
    # Computer Modern math faces + AMS symbols: only ever typeset equations.
    for font in ("CMMI10", "CMSY10", "CMEX10", "MSBM10", "MSAM7", "Euler-Regular"):
        assert _looks_like_math([_line_with_font(font)]), font


def test_math_subset_prefixes_are_recognised() -> None:
    # PyMuPDF reports subset fonts as "ABCDEF+CMMI10"; the family check must see through it.
    assert _looks_like_math([_line_with_font("ABCDEF+CMMI10")])


def test_modern_math_font_names_are_recognised() -> None:
    assert _looks_like_math([_line_with_font("STIXTwoMath-Regular")])
    assert _looks_like_math([_line_with_font("XITSMath-Regular")])


def test_latex_body_text_cmr10_is_not_math() -> None:
    # LaTeX prose is set in CMR10 - the same family family name must NOT be treated as math,
    # or every paragraph of a LaTeX paper would become an untranslated FORMULA block.
    assert not _looks_like_math([_line_with_font("CMR10", "ordinary paragraph text")])


def test_body_fonts_are_not_math() -> None:
    for font in ("NimbusRomNo9L-Regu", "DejaVuSans", "DMSans-Regular", "Helvetica"):
        assert not _looks_like_math([_line_with_font(font, "readable prose here")]), font


def test_paragraph_with_inline_math_stays_body() -> None:
    # A sentence that embeds inline symbols (x \in R) in math faces is still prose - only a
    # block with no prose face at all is a displayed equation.
    lines = [
        _line_with_font("NimbusRomNo9L-Regu", "We show that "),
        _line_with_font("CMMI10", "x"),
        _line_with_font("NimbusRomNo9L-Regu", " holds for every input."),
    ]
    assert not _looks_like_math(lines)


def test_short_cmr10_equation_with_math_face_is_formula() -> None:
    # Ghostscript-built academic PDFs keep CMR10 only for the roman fragments inside equations
    # ("= softmax"); body prose is Nimbus/Times. A short CMR10+CMMI block is a displayed
    # equation and must be FORMULA even though CMR10 alone is not math.
    lines = [
        _line_with_font("CMMI10", "A"),
        _line_with_font("CMR10", "i = softmax"),
    ]
    assert _looks_like_math(lines)


def test_long_cmr10_block_is_paragraph_not_equation() -> None:
    # In a raw dvips PDF the *body* is CMR10, so a long CMR10-bearing block with math spans
    # (inline variables in a paragraph) is prose - only short CMR10 blocks can be equations.
    line = _line_with_font("CMR10", "x " * 120)  # > 200 chars
    lines = [line, _line_with_font("CMMI10", "y")]
    assert not _looks_like_math(lines)


def test_mixed_block_with_any_math_span_is_math() -> None:
    # A displayed equation's line can carry both the symbol face and a roman fragment
    # (CMR10 for function names like "softmax"); one math span makes the whole block FORMULA.
    lines = [
        _line_with_font("CMR10", "MHA(x) = Concat"),
        _line_with_font("CMMI10", "x"),
    ]
    assert _looks_like_math(lines)


def test_single_column_roles_and_order(tmp_path: Path) -> None:
    src = tmp_path / "single.pdf"
    build_single_column(src)
    doc = read_pdf(src)
    assert len(doc.pages) == 1
    blocks = doc.pages[0].blocks_in_reading_order()
    roles = [b.role for b in blocks]
    assert roles == [BlockRole.HEADER, BlockRole.BODY, BlockRole.PAGE_NUMBER]
    orders = [b.order for b in blocks]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


def test_page_dimensions(tmp_path: Path) -> None:
    src = tmp_path / "single.pdf"
    build_single_column(src)
    doc = read_pdf(src)
    page = doc.pages[0]
    assert page.width == 400.0
    assert page.height == 500.0
    assert page.source_ref == "0"


def test_two_column_reading_order_not_interleaved(tmp_path: Path) -> None:
    src = tmp_path / "two_col.pdf"
    build_two_column(src)
    doc = read_pdf(src)
    blocks = doc.pages[0].blocks_in_reading_order()
    body_blocks = [b for b in blocks if b.role == BlockRole.BODY]
    assert len(body_blocks) == 2
    left, right = body_blocks
    assert left.bbox.x0 < right.bbox.x0
    assert left.order < right.order
    # Each column's own three sentences must stay together, not interleaved with the other.
    assert left.text.count("Left") == 3
    assert right.text.count("Right") == 3


def test_split_heading_lines_merge_into_one_block(tmp_path: Path) -> None:
    src = tmp_path / "split_heading.pdf"
    build_split_heading(src)
    doc = read_pdf(src)
    blocks = doc.pages[0].blocks_in_reading_order()
    heading_blocks = [b for b in blocks if "Hello" in b.text or "Today" in b.text]
    # The two lines must have become a single block, not two separate ones with different roles.
    assert len(heading_blocks) == 1
    heading = heading_blocks[0]
    assert heading.text == "Hello How Are\nYou Today?"
    assert len(heading.lines) == 2
    # The unrelated scattered words must not have been swept into the heading.
    assert "Scattered" not in heading.text
    assert "Words" not in heading.text


def test_scattered_layout_falls_back_to_top_to_bottom_order(tmp_path: Path) -> None:
    src = tmp_path / "scattered.pdf"
    build_scattered_no_columns(src)
    doc = read_pdf(src)
    blocks = doc.pages[0].blocks_in_reading_order()
    texts = [b.text for b in blocks]
    # No real columns exist here, so reading order must not jump backward in y - it must read
    # top to bottom even though `_cluster_columns` still splits these into x-bands.
    assert texts == ["Top block", "Middle block", "Bottom block"]


def test_running_header_and_footer_detected_across_pages(tmp_path: Path) -> None:
    src = tmp_path / "hf.pdf"
    build_running_header_footer(src)
    doc = read_pdf(src)
    assert len(doc.pages) == 3
    for i, page in enumerate(doc.pages, start=1):
        roles = {b.role: b for b in page.blocks}
        assert roles[BlockRole.HEADER].text == "Running Header Text"
        assert roles[BlockRole.FOOTER].text == "Confidential Draft"
        assert roles[BlockRole.PAGE_NUMBER].text == str(i)
        assert BlockRole.BODY in roles


def test_hyphenation_joined(tmp_path: Path) -> None:
    src = tmp_path / "hyphen.pdf"
    build_hyphenated(src)
    doc = read_pdf(src)
    text = doc.pages[0].blocks[0].text
    assert "hyphenation" in text
    assert "hyphen-" not in text


def test_bold_italic_spans(tmp_path: Path) -> None:
    src = tmp_path / "bi.pdf"
    build_bold_italic(src)
    doc = read_pdf(src)
    block = doc.pages[0].blocks[0]
    spans = block.lines[0].spans
    styles = {span.text.strip(): span.style for span in spans}
    assert styles["bold"].bold is True
    assert styles["bold"].italic is False
    assert styles["italic"].italic is True
    assert styles["italic"].bold is False


def test_background_art_does_not_become_a_block(tmp_path: Path) -> None:
    src = tmp_path / "bg.pdf"
    build_background_art(src)
    doc = read_pdf(src)
    # Only the text paragraph should turn into a Block; the rectangle/image are not text.
    assert len(doc.pages[0].blocks) == 1
    assert doc.pages[0].blocks[0].role == BlockRole.BODY


def test_span_style_has_hex_color(tmp_path: Path) -> None:
    src = tmp_path / "single.pdf"
    build_single_column(src)
    doc = read_pdf(src)
    span = doc.pages[0].blocks[0].lines[0].spans[0]
    assert span.style.color.startswith("#")
    assert len(span.style.color) == 7


def test_rotated_text_angles(tmp_path: Path) -> None:
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)
    by_text = {b.text: b for b in doc.pages[0].blocks}
    assert by_text["Sideways"].rotation == pytest.approx(-90.0, abs=0.5)
    assert abs(by_text["Upside Down"].rotation) == pytest.approx(180.0, abs=0.5)
    assert by_text["Noob"].rotation == pytest.approx(-18.8, abs=0.5)
    # The control paragraph is genuinely horizontal.
    control = next(b for b in doc.pages[0].blocks if "Ordinary horizontal" in b.text)
    assert control.rotation == pytest.approx(0.0, abs=0.5)


def test_mirrored_text_is_detected_and_flagged(tmp_path: Path) -> None:
    """Mirrored text is flagged; text merely rotated by the same angle is not.

    This was recorded as a known limitation for a long time, on the grounds that pymupdf's
    `get_text()` family reports only a flow-direction vector (`dir`) and axis-aligned boxes,
    never the sign of the glyph transform's determinant - so a horizontally-mirrored line and a
    genuinely 180-degree rotated line produce the identical `dir` and the identical `rotation`.

    That part is true and still is. What was wrong was the conclusion. `dir` cannot carry the
    determinant, but the glyphs themselves can: under any pure rotation a glyph extends from its
    baseline origin towards `dir` turned a quarter-turn, and mirroring flips that side while
    leaving `dir` alone. Measured across 0/45/90/180/270 degrees with and without a mirror, the
    projection is +0.65 for every upright case and -0.65 for every mirrored one.

    The pipeline still cannot write mirrored text back mirrored. It now says so instead of
    silently un-mirroring it.
    """
    src = tmp_path / "mirrored.pdf"
    build_mirrored_text(src)
    doc = read_pdf(src)
    by_text = {b.text: b for b in doc.pages[0].blocks}

    mirrored = by_text["Mirrored Label"]
    assert mirrored.rotation == pytest.approx(-180.0, abs=0.5)
    assert mirrored.needs_review is True
    assert "aynalan" in mirrored.review_reason

    control = next(b for b in doc.pages[0].blocks if "Ordinary horizontal" in b.text)
    assert control.needs_review is False


def test_ordinary_rotation_is_not_mistaken_for_mirroring(tmp_path: Path) -> None:
    """The other half of the claim, and the one that would hurt if it were wrong: flagging every
    rotated block "just in case" would swamp the review queue with correctly-rendered text.

    The 180-degree block reports the same `rotation` as the mirrored one in the test above, so
    this is the case any detector built on `dir` alone would get wrong.
    """
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)

    for block in doc.pages[0].blocks:
        assert block.needs_review is False, f"{block.text!r} wrongly flagged as mirrored"

    upside_down = next(b for b in doc.pages[0].blocks if b.text == "Upside Down")
    assert abs(upside_down.rotation) == pytest.approx(180.0, abs=0.5)


def test_rotated_lines_do_not_merge_with_differently_angled_neighbours(tmp_path: Path) -> None:
    """The shallow-angle label and the control paragraph sit close enough vertically that
    `_merge_wrapped_lines` would consider merging them if it ignored rotation."""
    src = tmp_path / "rotated.pdf"
    build_rotated_text(src)
    doc = read_pdf(src)
    noob = next(b for b in doc.pages[0].blocks if b.text == "Noob")
    assert "Ordinary" not in noob.text
    assert "Sideways" not in noob.text
