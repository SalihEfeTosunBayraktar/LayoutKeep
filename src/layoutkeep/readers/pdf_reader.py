"""PDF reader: turns a PDF's pages into a DocIR Document.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-pdf.md): pymupdf's own text-block
segmentation (`Page.get_text("dict")`) is used as the paragraph unit - it already groups
wrapped lines that belong together, including joining a hard-wrapped line back into its
paragraph. On top of that this module adds what pymupdf does not give for free:
  - reading order across multi-column layouts (`Block.order`)
  - hyphenated line-break joining
  - role classification: repeating running headers/footers, page numbers, headings, captions
This is one of only two modules allowed to `import pymupdf` (see CONTRACT.md §4).
"""

from __future__ import annotations

import base64
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    ImageRef,
    Line,
    Page,
    Span,
    Style,
)

_BOLD_FLAG = 1 << 4  # pymupdf span flag bit for bold
_ITALIC_FLAG = 1 << 1  # pymupdf span flag bit for italic
_SERIF_FLAG = 1 << 2  # pymupdf span flag bit for serifed, off the PDF's font descriptor

#: A block at least this wide relative to the page is treated as spanning all columns
#: (running headers/footers, titles) rather than belonging to one column.
_FULL_WIDTH_RATIO = 0.7
#: Top/bottom fraction of the page height considered header/footer territory.
_MARGIN_RATIO = 0.12
#: A short, mostly-digit block in the margin: "3", "- 3 -", "Page 3", "3/10".
_PAGE_NUMBER_RE = re.compile(r"^[\s\-–—.:|/\[\]()]*\d{1,4}[\s\-–—.:|/\[\]()]*$")
_TERMINAL_PUNCTUATION = ".!?…\"')"
_HYPHENS = "-­‐‑"
#: A body block whose font is at least this much larger than the document's body size reads as
#: a heading rather than a paragraph.
_HEADING_SIZE_RATIO = 1.15
#: Two lines/blocks within this many degrees of each other count as "the same angle" for merging
#: and role logic - pymupdf's `dir` vector carries floating-point noise even for text drawn dead
#: straight.
_ROTATION_MERGE_EPS_KEY = "merge.rotation_eps_deg"  # tunables key; the value is read where it is used
#: Caption text sits within this many points below an image and must not be much larger than it.
_CAPTION_GAP = 24.0


@dataclass(slots=True)
class _RawBlock:
    """A page's text block before reading order and role are decided."""

    block: Block
    top_margin: bool
    bottom_margin: bool


@dataclass(slots=True)
class _RawPage:
    page: Page
    blocks: list[_RawBlock] = field(default_factory=list)
    images: list[BBox] = field(default_factory=list)


def read_pdf(path: str | Path) -> Document:
    """Read a PDF file into a DocIR Document."""
    raw_pages: list[_RawPage] = []
    with pymupdf.open(str(path)) as src:
        for index in range(src.page_count):
            raw_pages.append(_read_page(src[index], index))

    doc = Document(source_path=str(path), source_format="pdf")
    _classify_roles(raw_pages)
    for rp in raw_pages:
        rp.page.blocks = [rb.block for rb in rp.blocks]
    doc.pages = [rp.page for rp in raw_pages]
    return doc


# --------------------------------------------------------------------------------------
# Per-page extraction
# --------------------------------------------------------------------------------------


def _read_page(page: pymupdf.Page, index: int) -> _RawPage:
    width, height = page.rect.width, page.rect.height
    top_edge = height * _MARGIN_RATIO
    bottom_edge = height * (1 - _MARGIN_RATIO)

    text_dict = page.get_text("dict")
    blocks: list[Block] = []
    for block_index, raw in enumerate(text_dict.get("blocks", [])):
        if raw.get("type") != 0:  # 0 = text, 1 = image; images carry no translatable text
            continue
        lines = _lines_from_raw(raw)
        if not lines or not any(line.text.strip() for line in lines):
            continue
        _join_hyphenation(lines)
        bbox = BBox(*raw["bbox"])
        blocks.append(
            Block(
                id=f"p{index}#{block_index}",
                role=BlockRole.FORMULA if _looks_like_math(lines) else BlockRole.BODY,
                bbox=bbox,
                lines=lines,
                rotation=_block_rotation(raw.get("lines", [])),
                align=_infer_alignment(bbox, width),
            )
        )

    # Mirrored text cannot be written back unmirrored by this pipeline, so it is flagged rather
    # than silently un-mirrored - a reader who is told is better off than one who is not
    # (CONTRACT.md). Detection is separate from `rotation` because `dir` cannot carry it.
    for box in _mirrored_boxes(page):
        for block in blocks:
            if _covered_by(box, block.bbox):
                block.needs_review = True
                block.review_reason = "metin aynalanmış, olduğu gibi geri yazılacak"

    blocks = _merge_wrapped_lines(_split_side_by_side_lines(blocks))

    order = _reading_order(blocks, width, height)
    for block, position in zip(blocks, order, strict=True):
        block.order = position

    images = [BBox(*info["bbox"]) for info in page.get_image_info()]
    page_images = _extract_images(page)

    raw_blocks = [
        _RawBlock(
            block=b,
            top_margin=b.bbox.y0 <= top_edge,
            bottom_margin=b.bbox.y1 >= bottom_edge,
        )
        for b in blocks
    ]
    return _RawPage(
        page=Page(
            number=index + 1,
            width=width,
            height=height,
            images=page_images,
            source_ref=str(index),
        ),
        blocks=raw_blocks,
        images=images,
    )


#: A glyph's offset from its own baseline origin, projected onto where "up" should be. Well
#: clear of zero for real text and safely below the ~0.65 the measurement produces, so it only
#: rejects degenerate glyphs - a space, or a char whose bbox collapsed.
_MIRROR_MIN_PROJECTION = 0.15

#: How much of a text span must sit inside a block's bbox before the span's mirroring is taken
#: to be the block's. Spans come from a different pymupdf call than blocks do, so they are
#: matched by geometry rather than by identity.
_MIRROR_OVERLAP = 0.5


def _span_is_mirrored(span: dict) -> bool:
    """True when this span's text transform has a negative determinant - the text is mirrored.

    `dir` is a flow-direction vector and cannot show this: a line mirrored horizontally and a
    line rotated 180 degrees report exactly the same `dir`. The glyphs still differ, though.
    Under any pure rotation a glyph extends from its baseline origin towards `dir` turned a
    quarter-turn; mirroring flips that side while leaving `dir` untouched. So the sign of the
    projection separates the two, at every angle.

    Measured across rotations of 0, 45, 90, 180 and 270 degrees with and without a mirror: the
    projection is +0.65 for all ten upright cases and -0.65 for all ten mirrored ones. The sign
    is what matters, not the magnitude, so there is no threshold to tune.
    """
    chars = span.get("chars") or []
    dx, dy = span.get("dir", (1.0, 0.0))
    up_x, up_y = dy, -dx
    votes = 0
    for char in chars[:12]:
        origin, bbox = char[2], char[3]
        offset_x = (bbox[0] + bbox[2]) / 2 - origin[0]
        offset_y = (bbox[1] + bbox[3]) / 2 - origin[1]
        length = math.hypot(offset_x, offset_y)
        if length < 1e-9:
            continue
        projection = (up_x * offset_x + up_y * offset_y) / length
        if abs(projection) < _MIRROR_MIN_PROJECTION:
            continue
        votes += 1 if projection < 0 else -1
    return votes > 0


def _mirrored_boxes(page) -> list[tuple[float, float, float, float]]:
    return [s["bbox"] for s in page.get_texttrace() if _span_is_mirrored(s)]


def _covered_by(box: tuple[float, float, float, float], bbox: BBox) -> bool:
    """Whether most of `box` lies inside `bbox`."""
    x0, y0, x1, y1 = box
    width = min(x1, bbox.x1) - max(x0, bbox.x0)
    height = min(y1, bbox.y1) - max(y0, bbox.y0)
    if width <= 0 or height <= 0:
        return False
    area = (x1 - x0) * (y1 - y0)
    return area > 0 and (width * height) / area >= _MIRROR_OVERLAP


def _extract_images(page) -> list[ImageRef]:
    """The page's pictures, with their bytes, so a rebuilding writer can redraw them.

    The bboxes alone were already read to help decide block roles; the pixels were thrown away.
    That was invisible while the only PDF writer edited a copy of the source and never had to
    reproduce a figure, and it meant every cross-format export lost every image in the document.

    One xref can be placed on a page more than once, so the bytes are decoded once and shared
    between placements.
    """
    doc = page.parent
    decoded: dict[int, tuple[str, str]] = {}
    out: list[ImageRef] = []
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if not xref:
            continue
        if xref not in decoded:
            try:
                extracted = doc.extract_image(xref)
            except (RuntimeError, ValueError):
                continue
            decoded[xref] = (
                base64.b64encode(extracted["image"]).decode("ascii"),
                str(extracted.get("ext", "png")).lower(),
            )
        data, fmt = decoded[xref]
        out.append(ImageRef(bbox=BBox(*info["bbox"]), data=data, fmt=fmt))
    return out


def _block_rotation(raw_lines: list[dict]) -> float:
    """Angle in degrees from a pymupdf text block's first line, taken straight from the `dir`
    unit vector as `atan2(dy, dx)`. A raw block can in principle mix lines at different angles,
    but that is not something real documents do, so the first line stands for the whole block -
    the merge step below still refuses to fold a *different*-angle block into this one.

    `dir` alone cannot tell a mirrored line from a rotated one - both report the identical
    vector, which is why this returns an angle and nothing more. The determinant's sign is
    recovered separately from glyph geometry; see `_span_is_mirrored`.
    """
    if not raw_lines:
        return 0.0
    dx, dy = raw_lines[0].get("dir", (1.0, 0.0))
    return round(math.degrees(math.atan2(dy, dx)), 2)


#: Fonts that only ever typeset mathematics. A block set in one of these is a formula, not
#: prose, and must not be sent to a translator (BlockRole.FORMULA is non-translatable).
#: CMR10 is deliberately absent: LaTeX sets *body text* in Computer Modern Roman too, so a
#: CMR10-only block is ordinary prose, not math. The faces below are the ones LaTeX uses for
#: the symbols and variables *inside* equations (CM math italic/symbol/extension, AMS) and
#: modern OpenType math fonts.
_MATH_FONT_MARKERS = (
    "CMEX",   # Computer Modern math extension (big operators, delimiters)
    "CMSY",   # Computer Modern math symbols
    "CMMI",   # Computer Modern math italic (variables: x, y, \alpha)
    "MSAM",   # AMS symbols A
    "MSBM",   # AMS symbols B
    "Euler",  # AMS Euler math
    "rsfs",   # Ralph Smith formal script (math)
    "math",   # any font with "math" in its name (STIX Math, XITS Math, Latin Modern Math)
)

#: Lowercased once at import; the block check compares against lowercased font names so a
#: subset-prefixed or case-shifted report ("ABCDEF+CMMI10", "cmmi10") still matches.
_MATH_FONT_MARKERS_LOWER = tuple(m.lower() for m in _MATH_FONT_MARKERS)

#: Common body-text faces. A paragraph that happens to contain an inline symbol set in a math
#: face (LaTeX sets \dag, \times, variables inline in CMSY/CMMI) must stay BODY and be
#: translated - only a block with NO prose face at all is a pure displayed equation.
#:
#: CMR10 (Computer Modern Roman) is intentionally NOT here: it is ambiguous. Ghostscript-built
#: PDFs (this repo's academic corpus) substitute the prose body with Nimbus/Times and keep
#: CMR10 only for the roman fragments *inside* equations ("= softmax"), so treating CMR10 as
#: prose would freeze those equations as BODY. Raw dvips PDFs instead set the whole body in
#: CMR10 - treating it as math would freeze every paragraph. The disambiguator below is
#: therefore structural, not font-based: a CMR10 block is an equation only when it is short
#: (a displayed equation fits in a couple of lines), and prose otherwise.
_PROSE_FONT_MARKERS = (
    "nimbus", "times", "dejavu", "helvetica", "arial", "dmsans", "calibri",
    "tinos", "arimo", "cousine", "caladea", "liberation", "noto", "roboto",
    "georgia", "verdana", "cambria", "garamond", "palatino",
)

#: Displayed equations built by TeX sit on their own, one to a few lines. A CMR10-bearing
#: block longer than this is body prose (LaTeX paragraph), not an equation.
_MAX_EQUATION_CHARS = 200


def _infer_alignment(bbox: BBox, page_width: float) -> str:
    """Infer a block's horizontal alignment from its x-position relative to the page.

    A centred block sits roughly symmetric around the page midline; a right-aligned block sits
    close to the right margin while a left-aligned one hugs the left. Thresholds are generous so
    full-width justified paragraphs (which span most of the page) are not misread as centred.
    Only applies to blocks that leave a real margin on at least one side, so a block that already
    fills the page stays "left"/justify rather than being guessed at.
    """
    if page_width <= 0:
        return "left"
    left_margin = bbox.x0
    right_margin = page_width - bbox.x1
    block_center = (bbox.x0 + bbox.x1) / 2.0
    page_center = page_width / 2.0

    # A block that spans nearly the whole page is justified/full-width, not centred.
    span = bbox.x1 - bbox.x0
    if span >= page_width * 0.8:
        return "left"

    # Centred: the block's middle sits near the page's middle, with balanced margins.
    if abs(block_center - page_center) <= page_width * 0.05 and min(left_margin, right_margin) > 0:
        return "center"
    # Right-aligned: hugged to the right edge, with a large left margin and small right one.
    if right_margin <= page_width * 0.05 and left_margin > page_width * 0.15:
        return "right"
    return "left"


def _looks_like_math(lines: list[Line]) -> bool:
    """True when a block is a displayed equation, not readable prose.

    Academic PDFs (LaTeX) render each displayed equation as its own text block. The block's
    faces are the math fonts (CMMI/CMSY/CMEX, AMS MSAM/MSBM) - never a prose face - and the
    glyphs often map to low/private-use code points (\\x10, \\uf8ee) that no model could
    translate. Sending them to a translator corrupts them; they are layout the reader must
    carry through untouched, exactly what BlockRole.FORMULA exists for.

    The check is deliberately conservative in both directions:
    - A prose face anywhere in the block (Nimbus/Times/DejaVu/...) keeps it BODY even when
      inline symbols use a math face - "We show x \\in R ..." is a sentence with inline
      math, not an equation, and must still be translated.
    - CMR10 alone is NOT math (LaTeX body prose is set in it), and a CMR10-bearing block is
      only classified as an equation when it is short enough to be one; a long multi-line
      CMR10 block is a paragraph.
    """
    has_math = False
    has_prose = False
    has_cmr10 = False
    total_chars = 0
    for line in lines:
        for span in line.spans:
            text = span.text or ""
            total_chars += len(text)
            font = (span.style.font_family or "").lower()
            if any(marker in font for marker in _MATH_FONT_MARKERS_LOWER):
                has_math = True
            if any(marker in font for marker in _PROSE_FONT_MARKERS):
                has_prose = True
            if "cmr" in font:
                has_cmr10 = True
    if not has_math or has_prose:
        return False
    # Pure math faces (no CMR10 at all): unambiguous equation.
    if not has_cmr10:
        return True
    # CMR10-bearing: equation only when short - a long block is a LaTeX paragraph whose
    # inline math spans happened to be the ones that matched.
    return total_chars <= _MAX_EQUATION_CHARS


def _lines_from_raw(raw: dict) -> list[Line]:
    lines: list[Line] = []
    for raw_line in raw.get("lines", []):
        spans = [_span_from_raw(s) for s in raw_line.get("spans", [])]
        spans = [s for s in spans if s.text]
        if not spans:
            continue
        lines.append(Line(spans=spans, bbox=BBox(*raw_line["bbox"])))
    return lines


def _span_from_raw(raw: dict) -> Span:
    flags = raw.get("flags", 0)
    font = raw.get("font", "")
    style = Style(
        font_family=font,
        size=round(float(raw.get("size", 0.0)), 2),
        bold=bool(flags & _BOLD_FLAG) or "bold" in font.lower(),
        italic=bool(flags & _ITALIC_FLAG) or "italic" in font.lower() or "oblique" in font.lower(),
        color=f"#{raw.get('color', 0):06x}",
        serif=bool(flags & _SERIF_FLAG),
    )
    return Span(text=raw.get("text", ""), bbox=BBox(*raw["bbox"]), style=style)


def _join_hyphenation(lines: list[Line]) -> None:
    """Merge `hyphen-` + `ation` at a line break into `hyphenation`, in place.

    Only applies when the break looks like a genuine word split: the line ends in a hyphen
    directly after a letter, and the next line starts with a lowercase letter.
    """
    i = 0
    while i < len(lines) - 1:
        spans = lines[i].spans
        if not spans or not spans[-1].text:
            i += 1
            continue
        last_span = spans[-1]
        tail = last_span.text
        if len(tail) < 2 or tail[-1] not in _HYPHENS or not tail[-2].isalpha():
            i += 1
            continue
        next_spans = lines[i + 1].spans
        if not next_spans or not next_spans[0].text or not next_spans[0].text[0].islower():
            i += 1
            continue
        joined_text = tail[:-1] + next_spans[0].text
        joined_span = Span(text=joined_text, bbox=last_span.bbox, style=last_span.style)
        # Keep everything on one Line so it reads as one word run; drop the now-empty next line
        # by folding its spans onto this one.
        lines[i].spans = [*spans[:-1], joined_span, *next_spans[1:]]
        del lines[i + 1]
        # Don't advance: the freshly merged line might itself end in a hyphen (rare but cheap to handle).


#: A vertical gap up to this many times the font size still reads as consecutive lines of the
#: same paragraph rather than the start of a new one.
_LINE_MERGE_GAP_KEY = "merge.line_gap_ratio"  # tunables key; the value is read where it is used

#: Rough line box height as a multiple of point size, used to turn a rotated line's centre
#: back into its glyph edges. Matches what `pdf_writer.py` assumes when it stacks them again.
_LINE_HEIGHT_KEY = "merge.line_height_ratio"  # tunables key; the value is read where it is used


#: Two lines belong to the same cell when their x-ranges overlap by at least this much of the
#: narrower one. Wrapped lines of a paragraph overlap almost completely; cells in a row do not
#: overlap at all.
_CELL_OVERLAP_KEY = "table.cell_overlap_ratio"  # tunables key; the value is read where it is used

#: How close two blocks' left edges must be, relative to the row's height, to count as the same
#: column. A table's columns line up; a paragraph's lines do not have columns to line up with.
_COLUMN_ALIGN_KEY = "table.column_align_ratio"  # tunables key; the value is read where it is used

def _x_overlap_ratio(a: BBox, b: BBox) -> float:
    """How much two boxes overlap horizontally, as a fraction of the narrower one."""
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    narrower = min(a.width, b.width)
    return overlap / narrower if narrower > 0 else 0.0


def _split_side_by_side_lines(blocks: list[Block]) -> list[Block]:
    """Split a block whose lines sit beside each other into one block per cell.

    MuPDF groups by proximity, so a table's header row - three short lines on one baseline -
    arrives as a single block. Read as a paragraph it becomes "Plate Cycles Deflection", and
    the translation of all three is written into the first cell's box.
    """
    out: list[Block] = []
    for block in blocks:
        if len(block.lines) < 2:
            out.append(block)
            continue

        groups: list[list[Line]] = []
        for line in sorted(block.lines, key=lambda ln: ln.bbox.x0):
            for group in groups:
                if any(_x_overlap_ratio(line.bbox, other.bbox) >= tunables.get(_CELL_OVERLAP_KEY)
                       for other in group):
                    group.append(line)
                    break
            else:
                groups.append([line])

        if len(groups) < 2:
            out.append(block)
            continue

        for index, group in enumerate(groups):
            bbox = group[0].bbox
            for line in group[1:]:
                bbox = bbox.union(line.bbox)
            out.append(
                Block(
                    id=f"{block.id}c{index}",
                    role=block.role,
                    bbox=bbox,
                    lines=sorted(group, key=lambda ln: ln.bbox.y0),
                    rotation=block.rotation,
                    align=block.align,
                    confidence=block.confidence,
                    needs_review=block.needs_review,
                    review_reason=block.review_reason,
                )
            )
    return out


#: Two blocks are the same kind of thing when their heights are within this factor. A cell and
#: the paragraph beside it differ by much more than that.
_HEIGHT_SIMILARITY_KEY = "table.height_similarity"  # tunables key; the value is read where it is used


#: How much of the shorter block two blocks must share vertically to be the same row.
_ROW_OVERLAP_KEY = "table.row_overlap_ratio"  # tunables key; the value is read where it is used


def _y_overlap_fraction(a: Block, b: Block) -> float:
    overlap = min(a.bbox.y1, b.bbox.y1) - max(a.bbox.y0, b.bbox.y0)
    shorter = min(a.bbox.height, b.bbox.height)
    return overlap / shorter if shorter > 0 else 0.0


def _similar_height(a: Block, b: Block) -> bool:
    taller = max(a.bbox.height, b.bbox.height)
    shorter = min(a.bbox.height, b.bbox.height)
    return shorter > 0 and taller / shorter <= tunables.get(_HEIGHT_SIMILARITY_KEY)


def _grid_blocks(blocks: list[Block]) -> set[str]:
    """Ids of blocks that sit in a grid - a table's cells.

    A row of cells and a line of a paragraph look alike to a merger that only asks about font
    size, vertical gap and horizontal overlap. What tells them apart is repetition: cells line
    up into columns across consecutive rows, and a paragraph has no columns to line up with.
    """
    # A row is blocks that share a band *and* a height. Without the height test the paragraph
    # in the next column joins the row - it spans several of them - and the row comes out one
    # member longer than the row below it, so the two never line up and the table is missed.
    # Only single-line blocks can be cells. A paragraph is many lines in one block, and two
    # paragraphs sitting side by side in a two-column page would otherwise look exactly like a
    # row of cells that repeats down the page.
    cells = [b for b in blocks if len(b.lines) <= 2]

    # Rows are grouped on how *much* two blocks overlap, not whether they touch at all. Two
    # tables on one page sit a few points out of step with each other, and a half-point overlap
    # was enough to chain one row to the next until a single band held 37 blocks from all over
    # the page.
    rows: list[list[Block]] = []
    for block in sorted(cells, key=lambda b: b.bbox.y0):
        for row in rows:
            if any(
                _y_overlap_fraction(block, other) >= tunables.get(_ROW_OVERLAP_KEY)
                and _similar_height(block, other)
                for other in row
            ):
                row.append(block)
                break
        else:
            rows.append([block])

    candidates = [sorted(row, key=lambda b: b.bbox.x0) for row in rows if len(row) >= 2]
    grid: set[str] = set()
    for index, row in enumerate(candidates):
        height = max(b.bbox.height for b in row) or 1.0
        for other in candidates[index + 1 :]:
            # Matched column by column rather than row against row. A page can hold two tables
            # whose rows interleave - the left column's table starting a few points below the
            # right column's - and then no two rows have the same number of cells, which is how
            # a whole page of tables went undetected.
            matched = [
                (a, b)
                for a in row
                for b in other
                if abs(a.bbox.x0 - b.bbox.x0) <= height * tunables.get(_COLUMN_ALIGN_KEY)
                and _similar_height(a, b)
            ]
            if len(matched) >= 2:
                grid.update(a.id for a, _ in matched)
                grid.update(b.id for _, b in matched)
    return grid


def _text_axes(bbox: BBox, rotation: float) -> tuple[float, float]:
    """A box's centre in the frame of text set at `rotation`: along the baseline, then across it.

    A rotated paragraph's lines step perpendicular to their baseline, so in page coordinates
    their axis-aligned boxes overlap each other instead of stacking, and the vertical gap between
    two consecutive lines comes out negative. Measured across the baseline instead, they stack
    exactly the way horizontal lines do. The boxes themselves cannot simply be rotated: the
    axis-aligned box of a 45-degree line is nearly square, and turning a square gives a bigger
    square, not the line back.
    """
    radians = math.radians(rotation)
    cos, sin = math.cos(radians), math.sin(radians)
    cx = (bbox.x0 + bbox.x1) / 2
    cy = (bbox.y0 + bbox.y1) / 2
    return cx * cos + cy * sin, -cx * sin + cy * cos


def _across_span(block: Block, rotation: float) -> tuple[float, float]:
    """Where a rotated block starts and ends across its baseline, padded out to its glyph edges.

    The block's own lines are measured, not the block, so a block that already holds several
    lines is compared from its last line rather than its middle.
    """
    centres = [_text_axes(line.bbox, rotation)[1] for line in block.lines]
    if not centres:
        centres = [_text_axes(block.bbox, rotation)[1]]
    half = block.dominant_style().size * tunables.get(_LINE_HEIGHT_KEY) / 2
    return min(centres) - half, max(centres) + half


def _along_reach(bbox: BBox) -> float:
    """An upper bound on how far a rotated line runs along its own baseline."""
    return math.hypot(bbox.width, bbox.height)


def _merge_wrapped_lines(blocks: list[Block]) -> list[Block]:
    """Merge text blocks that PyMuPDF split apart but that are really one paragraph.

    `get_text("dict")` usually already groups a paragraph's wrapped lines into a single block,
    so that grouping is used as-is elsewhere in this module. But on pages with irregular leading
    - notably a multi-line heading placed with extra line spacing - it can hand back each visual
    line as its own block. Two blocks merge here when they share the same dominant font size,
    sit close enough vertically to read as consecutive lines of one block rather than separate
    ones, and their x-ranges overlap. This runs before reading order and role classification, so
    a merged heading gets one position and one role instead of being scattered and split.
    """
    # Cells that line up into columns across rows are a table. Merging one row into the next
    # turns the whole thing into a single block whose translation is written into the first
    # cell, which is what the README's own comparison image was showing.
    in_grid = _grid_blocks(blocks)

    remaining = sorted(blocks, key=lambda b: b.bbox.y0)
    merged: list[Block] = []
    while remaining:
        current = remaining.pop(0)
        if current.id in in_grid:
            merged.append(current)
            continue
        while True:
            best_index: int | None = None
            best_gap = 0.0
            size = current.dominant_style().size
            rotated = abs(current.rotation) > tunables.get(_ROTATION_MERGE_EPS_KEY)
            # A tilted paragraph is measured along and across its own baseline, so that "the
            # line below this one" and "sits over the same span" mean what they mean for
            # upright text. Without it a rotated heading is never merged and each of its visual
            # lines is translated alone, out of the sentence it belongs to.
            if rotated:
                here_along, _ = _text_axes(current.bbox, current.rotation)
                _, here_end = _across_span(current, current.rotation)
            for i, candidate in enumerate(remaining):
                if abs(candidate.rotation - current.rotation) > tunables.get(_ROTATION_MERGE_EPS_KEY):
                    continue  # different angle - not the same paragraph however close it sits
                if rotated:
                    there_along, _ = _text_axes(candidate.bbox, current.rotation)
                    there_start, _ = _across_span(candidate, current.rotation)
                    gap = there_start - here_end
                    reach = max(_along_reach(current.bbox), _along_reach(candidate.bbox))
                    overlaps = abs(there_along - here_along) < reach / 2
                else:
                    gap = candidate.bbox.y0 - current.bbox.y1
                    overlaps = not (
                        current.bbox.x0 >= candidate.bbox.x1
                        or current.bbox.x1 <= candidate.bbox.x0
                    )
                if gap < 0 or size <= 0 or candidate.dominant_style().size != size:
                    continue
                if gap > size * tunables.get(_LINE_MERGE_GAP_KEY):
                    continue
                if candidate.id in in_grid:
                    continue  # a table cell, not the next line of this paragraph
                if not overlaps:
                    continue  # not stacked over the same span of the line above
                if best_index is None or gap < best_gap:
                    best_index, best_gap = i, gap
            if best_index is None:
                break
            candidate = remaining.pop(best_index)
            current = Block(
                id=current.id,
                role=current.role,
                bbox=current.bbox.union(candidate.bbox),
                lines=current.lines + candidate.lines,
                confidence=min(current.confidence, candidate.confidence),
                needs_review=current.needs_review or candidate.needs_review,
                rotation=current.rotation,
            )
        merged.append(current)
    return merged


# --------------------------------------------------------------------------------------
# Reading order across multi-column layouts
# --------------------------------------------------------------------------------------


def _reading_order(blocks: list[Block], page_width: float, page_height: float) -> list[int]:
    """Return, for each block (same order as input), its position in reading order.

    Margin blocks (running headers/footers, page numbers) are read first/last regardless of
    their width - a narrow, centred page number must not be treated as a column and sorted
    between two real body columns. Within the remaining body area, full-width blocks (section
    titles) act as horizontal separators; between two separators, column blocks are read
    column-major: all of the left column top-to-bottom, then the next column, never interleaved
    sentence by sentence.
    """
    if not blocks:
        return []
    top_edge = page_height * _MARGIN_RATIO
    bottom_edge = page_height * (1 - _MARGIN_RATIO)
    top_margin = sorted((b for b in blocks if b.bbox.y0 <= top_edge), key=lambda b: b.bbox.y0)
    margin_ids = {id(b) for b in top_margin}
    bottom_margin = sorted(
        (b for b in blocks if id(b) not in margin_ids and b.bbox.y1 >= bottom_edge),
        key=lambda b: b.bbox.y0,
    )
    margin_ids |= {id(b) for b in bottom_margin}
    body = [b for b in blocks if id(b) not in margin_ids]

    full = sorted(
        (b for b in body if b.bbox.width >= _FULL_WIDTH_RATIO * page_width),
        key=lambda b: b.bbox.y0,
    )
    columns = [b for b in body if b.bbox.width < _FULL_WIDTH_RATIO * page_width]
    bands = _cluster_columns(columns)
    use_bands = _looks_like_columns(bands)
    band_of: dict[int, int] = {}
    for band_index, band in enumerate(bands):
        for b in band:
            band_of[id(b)] = band_index

    boundaries = [b.bbox.y0 for b in full]

    def bucket(y0: float) -> int:
        return sum(1 for boundary in boundaries if boundary <= y0)

    buckets: dict[int, list[Block]] = {}
    for b in columns:
        buckets.setdefault(bucket(b.bbox.y0), []).append(b)
    for group in buckets.values():
        if use_bands:
            group.sort(key=lambda b: (band_of[id(b)], b.bbox.y0))
        else:
            # The bands do not look like real columns (see `_looks_like_columns`) - a scattered
            # layout has no single correct reading order, so fall back to plain top-to-bottom,
            # left-to-right instead of pretending the bands are columns to read one at a time.
            group.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))

    body_sequence: list[Block] = []
    for i in range(len(full) + 1):
        body_sequence.extend(buckets.get(i, []))
        if i < len(full):
            body_sequence.append(full[i])

    sequence = top_margin + body_sequence + bottom_margin
    position = {id(b): i for i, b in enumerate(sequence)}
    return [position[id(b)] for b in blocks]


def _cluster_columns(blocks: list[Block]) -> list[list[Block]]:
    """Greedily group blocks with overlapping x-ranges into left-to-right column bands."""
    if not blocks:
        return []
    bands: list[dict] = []
    for b in sorted(blocks, key=lambda b: b.bbox.x0):
        placed = False
        for band in bands:
            if b.bbox.x0 < band["x1"] and b.bbox.x1 > band["x0"]:
                band["x0"] = min(band["x0"], b.bbox.x0)
                band["x1"] = max(band["x1"], b.bbox.x1)
                band["blocks"].append(b)
                placed = True
                break
        if not placed:
            bands.append({"x0": b.bbox.x0, "x1": b.bbox.x1, "blocks": [b]})
    bands.sort(key=lambda band: band["x0"])
    for band in bands:
        band["blocks"].sort(key=lambda b: b.bbox.y0)
    return [band["blocks"] for band in bands]


#: At least this fraction of a band's blocks must have a same-height neighbour in another band
#: for the two to count as genuinely side by side, rather than an accidental x-split.
_COLUMN_MATCH_RATIO = 0.5


def _y_overlaps(a: Block, b: Block) -> bool:
    return a.bbox.y0 < b.bbox.y1 and a.bbox.y1 > b.bbox.y0


def _looks_like_columns(bands: list[list[Block]]) -> bool:
    """True when `_cluster_columns`' bands look like real side-by-side columns.

    A real multi-column layout has columns that coexist: a block in the left column sits next to
    a block in the right column at roughly the same height, because the reader's eye goes down
    one column and back up to the top of the next. A page with no real columns - text scattered
    at arbitrary positions - still gets split into x-bands by `_cluster_columns` whenever two
    unrelated blocks happen to share an x-range, but none of their individual blocks actually
    line up with a block in another band. Checking block-to-block overlap rather than each band's
    overall bounding y-range matters: one scattered band can itself chain several blocks that are
    far apart vertically (each only overlapping the next in x), which would otherwise stretch its
    bounding range across most of the page and make every other band look aligned with it.
    """
    if len(bands) < 2:
        return True
    for i in range(len(bands)):
        for j in range(i + 1, len(bands)):
            a, b = bands[i], bands[j]
            smaller, other = (a, b) if len(a) <= len(b) else (b, a)
            matches = sum(1 for blk in smaller if any(_y_overlaps(blk, o) for o in other))
            if matches / len(smaller) >= _COLUMN_MATCH_RATIO:
                return True
    return False


def _looks_cut_off(block: Block, bottom_edge: float) -> bool:
    if block.role != BlockRole.BODY:
        return False
    if block.bbox.y1 < bottom_edge:
        return False
    text = block.text.rstrip()
    return bool(text) and text[-1] not in _TERMINAL_PUNCTUATION


# --------------------------------------------------------------------------------------
# Role classification
# --------------------------------------------------------------------------------------


def _normalize_for_repetition(text: str) -> str:
    """Fold out page numbers so "Chapter 1 - 3" and "Chapter 1 - 4" compare equal."""
    return re.sub(r"\d+", "#", text.strip().lower())


def _classify_roles(raw_pages: list[_RawPage]) -> None:
    all_blocks = [rb.block for rp in raw_pages for rb in rp.blocks]
    body_sizes: list[tuple[float, int]] = []
    for b in all_blocks:
        for line in b.lines:
            for span in line.spans:
                body_sizes.append((span.style.size, len(span.text)))
    median_size = _weighted_median(body_sizes) if body_sizes else 0.0

    # First pass: page numbers (position + shape, no cross-page evidence needed).
    header_texts: dict[str, int] = {}
    footer_texts: dict[str, int] = {}
    for rp in raw_pages:
        for rb in rp.blocks:
            text = rb.block.text.strip()
            if not text or not (rb.top_margin or rb.bottom_margin):
                continue
            if _PAGE_NUMBER_RE.match(text):
                rb.block.role = BlockRole.PAGE_NUMBER
                continue
            key = _normalize_for_repetition(text)
            if rb.top_margin:
                header_texts[key] = header_texts.get(key, 0) + 1
            else:
                footer_texts[key] = footer_texts.get(key, 0) + 1

    single_page = len(raw_pages) == 1
    # On a single page there is no repetition to confirm a header/footer, so position is all we
    # have - but position alone is only trustworthy when it is unambiguous: a genuine header is
    # the one line sitting alone in the top margin. When several unrelated blocks land in the
    # margin band (a scattered layout, not a real page margin), none of them gets promoted; they
    # stay BODY and get translated, which is the safer default when the page's structure is
    # itself in doubt.
    def _is_short_margin_body(rb: _RawBlock, top: bool) -> bool:
        text = rb.block.text.strip()
        margin = rb.top_margin if top else rb.bottom_margin
        return rb.block.role == BlockRole.BODY and margin and bool(text) and len(text) <= 80

    top_candidates = (
        sum(1 for rb in raw_pages[0].blocks if _is_short_margin_body(rb, top=True))
        if single_page
        else 0
    )
    bottom_candidates = (
        sum(1 for rb in raw_pages[0].blocks if _is_short_margin_body(rb, top=False))
        if single_page
        else 0
    )

    # Second pass: repeating (or, on a single-page doc with one unambiguous candidate,
    # position-only) headers/footers.
    for rp in raw_pages:
        for rb in rp.blocks:
            if rb.block.role != BlockRole.BODY:
                continue
            text = rb.block.text.strip()
            if not text or not (rb.top_margin or rb.bottom_margin):
                continue
            key = _normalize_for_repetition(text)
            if rb.top_margin:
                repeated = header_texts.get(key, 0) >= 2
                if repeated or (single_page and top_candidates == 1 and len(text) <= 80):
                    rb.block.role = BlockRole.HEADER
            else:
                repeated = footer_texts.get(key, 0) >= 2
                if repeated or (single_page and bottom_candidates == 1 and len(text) <= 80):
                    rb.block.role = BlockRole.FOOTER

    # Third pass: headings/title and figure captions, on whatever is still plain body text.
    title_assigned = False
    for rp in raw_pages:
        for rb in rp.blocks:
            block = rb.block
            if block.role != BlockRole.BODY:
                continue
            dominant = block.dominant_style()
            if median_size and dominant.size >= median_size * _HEADING_SIZE_RATIO:
                if not title_assigned:
                    block.role = BlockRole.TITLE
                    title_assigned = True
                else:
                    block.role = BlockRole.HEADING
                continue
            if _near_image(block.bbox, rp.images):
                block.role = BlockRole.CAPTION

    # Fourth pass: flag the last body paragraph on a page as cut off if it runs into the bottom
    # margin without ending in terminal punctuation - it continues onto the next page/column.
    for rp in raw_pages:
        bottom_edge = rp.page.height * (1 - _MARGIN_RATIO)
        body = [rb.block for rb in rp.blocks if rb.block.role == BlockRole.BODY]
        if not body:
            continue
        last = max(body, key=lambda b: b.order)
        if _looks_cut_off(last, bottom_edge):
            last.continues = True


def _weighted_median(sizes: list[tuple[float, int]]) -> float:
    expanded: list[float] = []
    for size, weight in sizes:
        expanded.extend([size] * max(weight, 1))
    return statistics.median(expanded)


def _near_image(bbox: BBox, images: list[BBox]) -> bool:
    """True when `bbox` reads as a caption for one of `images`: directly below it, not much
    wider than it (a full-width body paragraph merely near a small illustration is not a caption)."""
    for img in images:
        overlaps_x = bbox.x0 < img.x1 and bbox.x1 > img.x0
        gap_below = bbox.y0 - img.y1
        narrow_enough = bbox.width <= img.width * 2.5
        if overlaps_x and narrow_enough and 0 <= gap_below <= _CAPTION_GAP:
            return True
    return False
