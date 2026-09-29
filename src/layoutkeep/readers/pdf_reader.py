"""PDF reader: turns a PDF's pages into a DocIR Document.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-pdf.md): pymupdf's own text-block
segmentation (`Page.get_text("dict")`) is used as the paragraph unit - it already groups
wrapped lines that belong together, including joining a hard-wrapped line back into its
paragraph. On top of that this module adds what pymupdf does not give for free:
  - reading order across multi-column layouts (`Block.order`)
  - hyphenated line-break joining
  - role classification: repeating running headers/footers, page numbers, headings, captions
pymupdf stays inside `readers/` and `writers/`: this module and its `_pdf_*` helpers may import it,
the core modules never do (see CONTRACT.md §4).

Bu modül giriş noktasıdır (`read_pdf`, sayfa okuma); taramalar, düzen modeli, tablolar, satır
birleştirme, okuma sırası ve roller `readers/_pdf_*.py` modüllerindedir. This module is the entry
point; scans, layout regrouping, tables, line merging, reading order and roles live in
`readers/_pdf_*.py`.
"""

from __future__ import annotations

import math
from pathlib import Path

import pymupdf

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.ocr.layout_detector import LayoutDetector
from layoutkeep.ocr.layout_vlm import ChatFn
from layoutkeep.readers._layout import infer_alignment, join_hyphenation
from layoutkeep.readers._nonprose import is_code_like, is_formula_like
from layoutkeep.readers._pdf_common import _MARGIN_RATIO, _RawBlock, _RawPage
from layoutkeep.readers._pdf_images import _extract_images
from layoutkeep.readers._pdf_layout_regroup import _regroup_by_layout
from layoutkeep.readers._pdf_line_merge import _merge_wrapped_lines, _split_side_by_side_lines
from layoutkeep.readers._pdf_math import _looks_like_math
from layoutkeep.readers._pdf_mirror import _covered_by, _mirrored_boxes
from layoutkeep.readers._pdf_reading_order import _reading_order
from layoutkeep.readers._pdf_roles import _classify_roles
from layoutkeep.readers._pdf_scan import _is_searchable_scan, _read_scanned_page
from layoutkeep.readers.image_reader import (
    is_scanned_page,
)

_BOLD_FLAG = 1 << 4  # pymupdf span flag bit for bold
_ITALIC_FLAG = 1 << 1  # pymupdf span flag bit for italic
_MONOSPACE_FLAG = 1 << 3  # pymupdf span flag bit for a monospaced face
_SERIF_FLAG = 1 << 2  # pymupdf span flag bit for serifed, off the PDF's font descriptor


def read_pdf(
    path: str | Path,
    *,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
) -> Document:
    """Read a PDF file into a DocIR Document.

    `classifier`, when given, is a vision model asked what each region of a SCANNED page is
    (see `ocr/layout_vlm.py`). Telling a heading from a displayed formula from a running
    header is the one judgement with no signal in the geometry, and every heuristic that
    tried it from the box height was calibrated on one page and broke another. It is
    optional and fail-safe: without it, or if the model cannot be reached, the page is read
    exactly as before.
    """
    raw_pages: list[_RawPage] = []
    with pymupdf.open(str(path)) as src:
        for index in range(src.page_count):
            raw_pages.append(_read_page(src[index], index, classifier=classifier, layout=layout))

    doc = Document(source_path=str(path), source_format="pdf")
    _classify_roles(raw_pages)
    for rp in raw_pages:
        rp.page.blocks = [rb.block for rb in rp.blocks]
    doc.pages = [rp.page for rp in raw_pages]
    return doc


# --------------------------------------------------------------------------------------
# Per-page extraction
# --------------------------------------------------------------------------------------


def _read_page(
    page: pymupdf.Page,
    index: int,
    *,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
) -> _RawPage:
    width, height = page.rect.width, page.rect.height
    top_edge = height * _MARGIN_RATIO
    bottom_edge = height * (1 - _MARGIN_RATIO)

    # How much of the page is picture: a scan is a page that IS an image, and OCR needs
    # something to read. Computed here because `image_reader` may not import pymupdf.
    page_area = width * height
    covered = sum(
        (info["bbox"][2] - info["bbox"][0]) * (info["bbox"][3] - info["bbox"][1])
        for info in page.get_image_info()
    )
    coverage = covered / page_area if page_area > 0 else 0.0
    if is_scanned_page(page.get_text(), page_area, coverage) or _is_searchable_scan(page, coverage):
        return _read_scanned_page(
            page,
            index,
            top_edge=top_edge,
            bottom_edge=bottom_edge,
            classifier=classifier,
            layout=layout,
        )

    text_dict = page.get_text("dict")
    blocks: list[Block] = []
    for block_index, raw in enumerate(text_dict.get("blocks", [])):
        if raw.get("type") != 0:  # 0 = text, 1 = image; images carry no translatable text
            continue
        lines = _lines_from_raw(raw)
        if not lines or not any(line.text.strip() for line in lines):
            continue
        join_hyphenation(lines)
        bbox = BBox(*raw["bbox"])
        blocks.append(
            Block(
                id=f"p{index}#{block_index}",
                role=BlockRole.FORMULA if _looks_like_math(lines) else BlockRole.BODY,
                bbox=bbox,
                lines=lines,
                rotation=_block_rotation(raw.get("lines", [])),
                align=infer_alignment(bbox, width),
            )
        )

    # Mirrored text cannot be written back unmirrored by this pipeline, so it is flagged rather
    # than silently un-mirrored - a reader who is told is better off than one who is not
    # (CONTRACT.md). Detection is separate from `rotation` because `dir` cannot carry it.
    for box in _mirrored_boxes(page):
        for block in blocks:
            if _covered_by(box, block.bbox):
                block.needs_review = True
                block.review_reason = "REVIEW_MIRROR_TEXT"

    from_model: list[Block] = []
    if layout is not None:
        blocks, from_model = _regroup_by_layout(page, index, blocks, layout)
    # The rules only see what the model did not place: run over a table of contents the model
    # split into entries, "merge wrapped lines" would glue the entries back together.
    blocks = _merge_wrapped_lines(_split_side_by_side_lines(blocks)) + from_model

    # Alignment is decided once every block has its final lines, from those lines: a paragraph
    # PyMuPDF delivered as single-line pieces, then merged, is judged as the paragraph it became.
    for block in blocks:
        block.align = infer_alignment(
            block.bbox, width, [line.bbox for line in block.lines if line.bbox is not None]
        )
        # Code is set in a monospaced face; a block entirely in one is code, and translating it
        # changes the program the document prints (Think Python came back with the strings inside
        # print() calls translated). A PDF does not always say so - a LaTeX paper's verbatim
        # fragments are set in an ordinary face - so the text's own shape is asked as well
        # (`_nonprose.is_code_like`), which is what catches arXiv's "trim_offsets=True,
        # use_regex=True)": code the retry ladder could only ever be answered with.
        if block.role in (BlockRole.BODY, BlockRole.LIST, BlockRole.TABLE) and (
            _all_monospace(block) or is_code_like(block.text)
        ):
            block.role = BlockRole.CODE
        elif block.role in (BlockRole.BODY, BlockRole.LIST) and is_formula_like(block.text):
            # An equation in an ordinary face: `_looks_like_math` judges equations by their faces,
            # and a paper sets some of them in the body font.
            block.role = BlockRole.FORMULA

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


def _all_monospace(block: Block) -> bool:
    spans = [span for line in block.lines for span in line.spans if span.text.strip()]
    return bool(spans) and all(span.style.monospace for span in spans)


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
        monospace=bool(flags & _MONOSPACE_FLAG),
    )
    return Span(text=raw.get("text", ""), bbox=BBox(*raw["bbox"]), style=style)
