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
import itertools
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image

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
from layoutkeep.ocr.engine import TextBox
from layoutkeep.ocr.layout_detector import LABEL_TO_ROLE, LayoutDetector, resolve_duplicates
from layoutkeep.ocr.layout_vlm import ChatFn
from layoutkeep.readers._layout import infer_alignment, join_hyphenation
from layoutkeep.readers._nonprose import is_code_like, is_formula_like, is_prose_label
from layoutkeep.readers._segment import segment
from layoutkeep.readers.image_reader import (
    expected_characters,
    is_scanned_page,
    needs_higher_resolution,
    page_from_rendered_page,
)

_BOLD_FLAG = 1 << 4  # pymupdf span flag bit for bold
_ITALIC_FLAG = 1 << 1  # pymupdf span flag bit for italic
_MONOSPACE_FLAG = 1 << 3  # pymupdf span flag bit for a monospaced face
_SERIF_FLAG = 1 << 2  # pymupdf span flag bit for serifed, off the PDF's font descriptor

#: A block at least this wide relative to the page is treated as spanning all columns
#: (running headers/footers, titles) rather than belonging to one column.
_FULL_WIDTH_RATIO = 0.7
#: Top/bottom fraction of the page height considered header/footer territory.
_MARGIN_RATIO = 0.12
#: A short, mostly-digit block in the margin: "3", "- 3 -", "Page 3", "3/10".
_PAGE_NUMBER_RE = re.compile(r"^[\s\-–—.:|/\[\]()]*\d{1,4}[\s\-–—.:|/\[\]()]*$")
_TERMINAL_PUNCTUATION = ".!?…\"')"
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


#: Resolution a born-digital page is rendered at for the layout model. The model resizes to 640px
#: whatever it is given, so this only needs to keep small type legible to it.
_DIGITAL_LAYOUT_DPI = 100

#: Regions whose lines are separate items, not a paragraph: a table of contents is one entry per
#: line, a table one cell per line, a figure one label per line.
_ONE_BLOCK_PER_LINE = frozenset({"document_index", "table", "form", "key_value_region", "picture"})

#: How much of a line has to lie inside a region to belong to it.
_DIGITAL_REGION_MEMBERSHIP = 0.5


#: Lines of one table cell sit this close: within a line spacing of each other, left edges aligned.
_CELL_GAP = 0.6


def _horizontal_rules(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """The page's horizontal rules: what separates one table row from the next."""
    return [d["rect"] for d in page.get_drawings() if d["rect"].height <= 1.5 and d["rect"].width >= 5]


def _label_role(role: BlockRole, group: list[Line]) -> BlockRole:
    """A figure's line becomes a translated label when the setting is on and it reads as words.

    Off by default (translation.figure_text): diagram labels are mostly names and signals, and
    translating them broke diagrams before (Think Python p. 97). Names, code and pin runs stay
    part of the picture even when it is on (`_nonprose.is_prose_label`).
    """
    if role is not BlockRole.FIGURE or not tunables.get("translation.figure_text"):
        return role
    text = " ".join(span.text for line in group for span in line.spans)
    return BlockRole.FIGURE_LABEL if is_prose_label(text) else role


def _table_cells(lines: list[Line], rules: list[pymupdf.Rect], line_height: float) -> list[list[Line]]:
    """A table's lines grouped into cells: one block per cell, not one per line.

    Arm E, tr_shk_2828: a cell wrapped over "Mülki / İdare / Amirliği" came out as three blocks,
    each word translated alone ("aybaşında" -> "at the full moon") and too long for its one-line
    box. Lines join a cell when they are stacked in its column (left edges within a line height, or
    overlapping by half the narrower line for a centred cell),
    a line spacing apart at most, and no rule runs between them - a rule or a wider gap is a row.
    """
    groups: list[list[Line]] = []
    blank: list[list[Line]] = []
    for line in lines:  # sorted top to bottom
        if not "".join(span.text for span in line.spans).strip():
            blank.append([line])  # a blank line joins no cell and separates none
            continue
        box = line.bbox
        home = None
        for group in reversed(groups):
            last = group[-1].bbox
            if box.y0 < last.y1 - 0.5 * line_height:
                # On the same row: a piece of a justified line inside the cell's width belongs to
                # it ("... tabi personel kadroları Mülki İdare" came as four pieces); one beside it
                # is the next column.
                left = min(line.bbox.x0 for line in group)
                right = max(line.bbox.x1 for line in group)
                if left - 1 <= box.x0 and box.x1 <= right + 1:
                    home = group
                    break
                continue
            overlap = min(last.x1, box.x1) - max(last.x0, box.x0)
            narrower = min(last.x1 - last.x0, box.x1 - box.x0)
            aligned = abs(last.x0 - box.x0) <= line_height or overlap >= 0.5 * narrower
            if not aligned or box.y0 - last.y1 > _CELL_GAP * line_height:
                continue
            ruled = any(
                last.y1 - 1 <= rule.y0 <= box.y0 + 1 and rule.x0 < box.x1 and rule.x1 > box.x0
                for rule in rules
            )
            if not ruled:
                home = group
            break
        if home is None:
            groups.append([line])
        else:
            home.append(line)
    return groups + blank


def _regroup_by_layout(
    page: pymupdf.Page, index: int, blocks: list[Block], layout: LayoutDetector
) -> tuple[list[Block], list[Block]]:
    """Group a born-digital page's lines by the layout model's regions.

    Regions come from the model, looking at the rendered page; text, fonts and positions still
    come from the PDF, so nothing is re-recognised. Returns (blocks the model did not claim, for
    the existing rules; blocks built from the model's regions).

    Campaign, NIST SP 800-12 page 6: a table of contents came out with its entries run together,
    because the rules merged its lines into paragraphs. The model labels that page
    `document_index`, and each of its lines is one entry.

    Rotated text is left to the rules: its line boxes are not what the model sees upright.
    """
    pixmap = page.get_pixmap(dpi=_DIGITAL_LAYOUT_DPI)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    sx, sy = page.rect.width / pixmap.width, page.rect.height / pixmap.height
    regions = [
        (r.label, BBox(r.bbox[0] * sx, r.bbox[1] * sy, r.bbox[2] * sx, r.bbox[3] * sy))
        for r in resolve_duplicates(layout.detect(image))
    ]
    if not regions:
        return blocks, []

    unclaimed: list[Block] = []
    members: dict[int, list[Line]] = {}
    for block in blocks:
        if abs(block.rotation) > 1e-3:
            unclaimed.append(block)
            continue
        # The unclaimed lines, in runs of consecutive ones: a claimed line ends the run above it.
        # Leftovers are one paragraph only where nothing else sits between them - the box is what
        # the writer draws the translation into. Turkish Penal Code page 2 (a Word-generated PDF)
        # arrived as ONE pymupdf block of 43 lines holding the whole page, and the union box of its
        # leftovers was y 83..418, 335 pt tall: 'Madde 175', a heading at y 130 and '(2) Kara...'
        # at y 324-346 in one block, drawn as a strip at the top of the page while the places those
        # lines came from were left blank.
        runs: list[list[Line]] = []
        current: list[Line] | None = None
        for line in block.lines:
            owner = _owning_region(line.bbox, regions) if line.bbox is not None else None
            if owner is not None:
                members.setdefault(owner, []).append(line)
                current = None
                continue
            # A line of spaces is no part of a paragraph: on the Turkish Penal Code one sat on a
            # heading's row, joined the article's run and stretched its box over the heading (L7).
            if not "".join(span.text for span in line.spans).strip():
                continue
            if current is None:
                current = []
                runs.append(current)
            current.append(line)
        for position, run in enumerate(runs):
            box = run[0].bbox
            for line in run[1:]:
                if line.bbox is not None:
                    box = line.bbox if box is None else box.union(line.bbox)
            unclaimed.append(
                Block(
                    # The first run keeps the block's own id - it is that block as the reading
                    # order, the table grid and the review flags knew it; the later ones are
                    # numbered off it, the way the region-built blocks are (`#m…`).
                    id=block.id if position == 0 else f"{block.id}.{position}",
                    role=block.role, bbox=box or block.bbox, lines=run,
                    rotation=block.rotation, align=block.align,
                    needs_review=block.needs_review, review_reason=block.review_reason,
                )
            )

    width = page.rect.width
    heights = [
        line.bbox.y1 - line.bbox.y0 for block in blocks for line in block.lines if line.bbox is not None
    ]
    line_height = statistics.median(heights) if heights else 1.0
    rules: list[pymupdf.Rect] | None = None  # read once, only when the page has a table
    built: list[Block] = []
    for owner, lines in sorted(members.items()):
        label, _box = regions[owner]
        lines.sort(key=lambda line: (line.bbox.y0, line.bbox.x0))
        if label == "table":
            if rules is None:
                rules = _horizontal_rules(page)
            groups = _table_cells(lines, rules, line_height)
        elif label in _ONE_BLOCK_PER_LINE:
            groups = [[line] for line in lines]
        else:
            # A region can hold more than one column - a references page's "[SP800-57 part 1]" label
            # beside its entry came as one region, and sorted by height the label was interleaved
            # into the entry. The page's whitespace separates them, as it does on scanned pages.
            groups = _cut_by_whitespace(lines, line_height)
        if label == "picture":
            # A picture's text is part of the picture and stays as it is, as on scanned pages: a
            # stack diagram's labels translated line by line renamed its variables ("letters" ->
            # "harfler"), changed a value ('c' -> 'k') and lost "__main__" (Think Python p. 97).
            role = BlockRole.FIGURE
        elif label == "table":
            role = BlockRole.TABLE
        elif label in _ONE_BLOCK_PER_LINE:
            role = BlockRole.BODY
        else:
            role = LABEL_TO_ROLE.get(label, BlockRole.BODY)
        for group in groups:
            box = group[0].bbox
            for line in group[1:]:
                box = box.union(line.bbox)
            built.append(
                Block(
                    id=f"p{index}#m{owner}.{len(built)}", role=_label_role(role, group), bbox=box,
                    lines=group,
                    align=infer_alignment(box, width),
                )
            )
    if tunables.get("translation.figure_text"):
        taken = [b.bbox for b in [*unclaimed, *built]]
        for owner, (label, box) in enumerate(regions):
            if label == "picture":
                built.extend(_raster_labels(page, index, owner, box, taken))
    return unclaimed, built


#: Resolution a picture is read at for its labels, and the least OCR confidence a label is taken at.
_RASTER_LABEL_DPI = 200
_RASTER_LABEL_CONFIDENCE = 0.8
_raster_engine = None


def _raster_labels(page: pymupdf.Page, index: int, owner: int, box: BBox, taken: list[BBox]) -> list[Block]:
    """Labels read from a picture's pixels on a born-digital page (translation.figure_text on).

    A diagram in a slide deck or a scanned figure pasted into a PDF has its words in the image, not
    in the text layer, so the text-layer rule never sees them. OCR reads the region; a line that
    reads as words (`is_prose_label`), that OCR is sure of, and that no text-layer block already
    covers becomes a FIGURE_LABEL marked `raster`, which the writer erases from the picture and
    redraws translated. Names and signals stay part of the picture.
    """
    global _raster_engine
    if _raster_engine is None:
        from layoutkeep.ocr.engine import RapidOcrEngine

        _raster_engine = RapidOcrEngine()
    clip = pymupdf.Rect(box.x0, box.y0, box.x1, box.y1)
    if clip.is_empty:
        return []
    pixmap = page.get_pixmap(dpi=_RASTER_LABEL_DPI, clip=clip)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    scale = 72.0 / _RASTER_LABEL_DPI
    labels: list[Block] = []
    for found in _raster_engine.recognize(image):
        text = " ".join(found.text.split())
        if found.confidence < _RASTER_LABEL_CONFIDENCE or not is_prose_label(text):
            continue
        x0, y0, x1, y1 = found.bbox
        bbox = BBox(clip.x0 + x0 * scale, clip.y0 + y0 * scale, clip.x0 + x1 * scale, clip.y0 + y1 * scale)
        if any(_overlap_share(bbox, other) > 0.3 for other in taken):
            continue
        style = Style(size=round((bbox.y1 - bbox.y0) * 0.8, 1))
        labels.append(
            Block(
                id=f"p{index}#r{owner}.{len(labels)}", role=BlockRole.FIGURE_LABEL, bbox=bbox,
                lines=[Line(spans=[Span(text=text, bbox=bbox, style=style)], bbox=bbox)],
                confidence=found.confidence, raster=True,
            )
        )
    return labels


def _overlap_share(a: BBox, b: BBox) -> float:
    """How much of `a` lies inside `b`."""
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    area = max(1e-6, (a.x1 - a.x0) * (a.y1 - a.y0))
    return max(0.0, w) * max(0.0, h) / area


def _cut_by_whitespace(lines: list[Line], line_height: float) -> list[list[Line]]:
    """Split a region's lines at the page's structural gaps (see `readers/_segment.py`)."""
    stand_ins = [
        [TextBox(text=str(i), bbox=(ln.bbox.x0, ln.bbox.y0, ln.bbox.x1, ln.bbox.y1), confidence=1.0)]
        for i, ln in enumerate(lines)
    ]
    groups = [
        [lines[int(stand_in[0].text)] for stand_in in region.lines]
        for region in segment(stand_ins, line_height=line_height)
    ]
    return [
        paragraph
        for group in groups
        for part in _split_side_by_side_rows(group)
        for paragraph in _split_at_blank_lines(part, line_height)
    ]


#: A gap between two stacked lines of one region at least this many times the region's usual gap
#: between lines is a blank line between paragraphs.
_PARAGRAPH_GAP_FACTOR = 3.0


def _split_at_blank_lines(lines: list[Line], line_height: float) -> list[list[Line]]:
    """Split stacked lines where a blank line separates paragraphs.

    Held-out Wikipedia "Printing press", page 9: one text region held the whole page, and its four
    paragraphs, 15 pt apart against 2.5-3 pt between lines, stayed under the whitespace cut's
    threshold of 1.2 line heights (15.9 pt) - one 4,000-character block the model never answered, and
    the page was lost. Measured against the region's own spacing, a blank line is unmistakable; half
    a line height is the least a gap must be, so tight leading does not turn every line into one.
    """
    ordered = sorted(lines, key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
    # Lines set tighter than their boxes overlap a little: that is a gap of nothing, not less.
    gaps = [max(b.bbox.y0 - a.bbox.y1, 0.0) for a, b in itertools.pairwise(ordered)]
    if len(gaps) < 2:
        return [lines]
    threshold = max(_PARAGRAPH_GAP_FACTOR * statistics.median(gaps), 0.5 * line_height)
    parts: list[list[Line]] = [[ordered[0]]]
    for gap, line in zip(gaps, ordered[1:], strict=True):
        if gap >= threshold:
            parts.append([line])
        else:
            parts[-1].append(line)
    return parts


def _split_side_by_side_rows(lines: list[Line]) -> list[list[Line]]:
    """Split a group where two lines sit side by side on one row, at the gap between them.

    Two lines on the same row cannot be one run of text, however narrow the gap: NIST's one-line
    reference labels ("[SP800-39]", x 77-136) sit 18 pt from their entries (x 154) - just under the
    whitespace threshold for 16 pt lines - and were read into the middle of the entry.
    """
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            overlap = min(a.bbox.y1, b.bbox.y1) - max(a.bbox.y0, b.bbox.y0)
            shorter = min(a.bbox.y1 - a.bbox.y0, b.bbox.y1 - b.bbox.y0)
            if shorter <= 0 or overlap < shorter * 0.5:
                continue
            # A footnote mark set as its own tiny line beside a word is not a column.
            if min(a.bbox.x1 - a.bbox.x0, b.bbox.x1 - b.bbox.x0) < 2 * shorter:
                continue
            left, right = (a, b) if a.bbox.x1 <= b.bbox.x0 else (b, a) if b.bbox.x1 <= a.bbox.x0 else (None, None)
            if left is None:
                continue
            cut = (left.bbox.x1 + right.bbox.x0) / 2
            # Think Python p. 139: a justified line came out as two lines around a stretched space.
            # A paragraph's other lines run across that gap; two side-by-side columns leave it empty.
            if any(ln.bbox.x0 < cut < ln.bbox.x1 for ln in lines):
                continue
            before =sorted((ln for ln in lines if ln.bbox.x1 <= cut), key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
            after = sorted((ln for ln in lines if ln.bbox.x1 > cut), key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
            if before and after:
                return _split_side_by_side_rows(before) + _split_side_by_side_rows(after)
    return [lines]


def _owning_region(box: BBox, regions: list[tuple[str, BBox]]) -> int | None:
    """The smallest region holding at least half of `box`."""
    area = max((box.x1 - box.x0) * (box.y1 - box.y0), 1e-6)
    best, best_area = None, float("inf")
    for i, (_label, region) in enumerate(regions):
        ix = max(0.0, min(box.x1, region.x1) - max(box.x0, region.x0))
        iy = max(0.0, min(box.y1, region.y1) - max(box.y0, region.y0))
        size = (region.x1 - region.x0) * (region.y1 - region.y0)
        if ix * iy / area >= _DIGITAL_REGION_MEMBERSHIP and size < best_area:
            best, best_area = i, size
    return best


#: Resolution the page is rasterised at before OCR. Measured on page 61 of
#: `computer-systems-Architecture.pdf` (a 600-DPI scan): 200 DPI recovered all 47 text boxes at
#: 0.96 mean confidence, while 300 DPI cost ~2x the pixels and garbled a line the lower
#: resolution read cleanly. Higher is not automatically better - the recognition model has its
#: own preferred glyph height.
_SCAN_OCR_DPI = 200.0

#: Resolution a badly-read page is rendered at for its second pass (see
#: `image_reader.needs_higher_resolution`). Page 54 of the same book is why: at 200 DPI a clean
#: line of type came out as "Sin os -ns ( s ms o ong", and at 300 it reads correctly, recovering
#: 9.4% more characters on that page. Across six pages the same change is worth only +1.5%, so
#: it is not the default - it is what a page gets when the cheap pass reports too much doubt.
_SCAN_OCR_RETRY_DPI = 300.0


def _ocr_at(
    page: pymupdf.Page,
    index: int,
    dpi: float,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
):
    """Rasterise `page` at `dpi` and hand the pixels to OCR."""
    pixmap = page.get_pixmap(dpi=int(dpi))
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    return page_from_rendered_page(
        image,
        number=index + 1,
        source_ref=str(index),
        dpi=dpi,
        width_pt=page.rect.width,
        height_pt=page.rect.height,
        classifier=classifier,
        layout=layout,
    )


#: Text render mode 3: glyphs that are laid out but not painted - the searchable layer a scanner
#: or archive.org puts over a page image.
_INVISIBLE_TEXT = 3


def _is_searchable_scan(page: pymupdf.Page, coverage: float) -> bool:
    """True when an image covers the page and most of its text is invisible.

    A searchable scan carries a full OCR text layer, so by text density it looks born digital;
    read that way, the writer removed the invisible layer and drew the translation over the
    scanned English, which is pixels and stays. What a reader actually sees is decided by
    visibility: when most characters are not painted, the page is its image. Two of the
    campaign's five books are built this way (archive.org "Text PDF"), and so were pages 4-10 of
    the NASA report.
    """
    if coverage < tunables.get("reader.scan_image_coverage_layer"):
        return False
    visible = invisible = 0
    for trace in page.get_texttrace():
        count = len(trace.get("chars", ()))
        if trace.get("type") == _INVISIBLE_TEXT:
            invisible += count
        else:
            visible += count
    return invisible > visible


#: A searchable scan's image is the page. Majority coverage is the lowest that can mean that; a
#: page with a picture beside invisible text is not a scan of the whole page.
_SCANNED_IMAGE_COVERAGE_FOR_LAYER = 0.5


def _read_scanned_page(
    page: pymupdf.Page,
    index: int,
    *,
    top_edge: float,
    bottom_edge: float,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
) -> _RawPage:
    """A page with no text layer: rasterise it and let OCR find the text.

    Without this a scanned PDF reads as zero blocks and the app reports that there is nothing to
    translate - which is what `computer-systems-Architecture.pdf` (524 pages, no text layer at
    all) did. The OCR itself lives in `readers/image_reader.py`; this only supplies the pixels,
    because CONTRACT.md keeps the pymupdf import on this side of the boundary.
    """
    ocr_page = _ocr_at(page, index, _SCAN_OCR_DPI, classifier, layout)
    if needs_higher_resolution(ocr_page):
        # Enough of the page came back doubtful to be worth the extra pixels. Both passes are
        # kept and the better one wins, judged on how much text each recovered rather than on
        # how sure it sounds: page 61 of this book reads a line correctly at 200 and garbles it
        # at 300, and on page 451 the surer pass is the one that read 65 characters fewer.
        retry = _ocr_at(page, index, _SCAN_OCR_RETRY_DPI, classifier, layout)
        if expected_characters(retry) > expected_characters(ocr_page):
            ocr_page = retry
    ocr_page.scanned = True
    # The scan itself is the page's only picture; writers that rebuild the document need it, and
    # the pdf writer needs it to paint over the burnt-in source text.
    ocr_page.images = _extract_images(page)

    raw_blocks = [
        _RawBlock(
            block=b,
            top_margin=b.bbox.y0 <= top_edge,
            bottom_margin=b.bbox.y1 >= bottom_edge,
        )
        for b in ocr_page.blocks
    ]
    return _RawPage(page=ocr_page, blocks=raw_blocks, images=[img.bbox for img in ocr_page.images])


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
        monospace=bool(flags & _MONOSPACE_FLAG),
    )
    return Span(text=raw.get("text", ""), bbox=BBox(*raw["bbox"]), style=style)


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


def _hyphen_parents(lines: list[Line]) -> dict[int, Line]:
    """For each line that continues the one above it across a line break, that line.

    Keyed by `id(line)` - lines are not hashable and `Line` compares by value, which two blank
    lines of a table would satisfy.

    The test is the one the hyphen join is refused on: the line above ends in a hyphen after a
    letter and this one starts lowercase. Where the join *did* run there is nothing left to pair -
    the fragment already moved up - so this only ever fires on the breaks the join leaves alone,
    a URL or a path whose hyphen is part of the text.
    """
    parents: dict[int, Line] = {}
    ordered = sorted(lines, key=lambda ln: ln.bbox.y0)
    for index, line in enumerate(ordered[1:], start=1):
        above = ordered[index - 1]
        text = above.text
        if len(text) < 2 or text[-1] not in "-­‐‑" or not text[-2].isalpha():
            continue
        if not line.text or not line.text[0].islower():
            continue
        parents[id(line)] = above
    return parents


def _cell_groups(lines: list[Line]) -> list[list[Line]]:
    """Group one block's lines into columns: each group is one cell of the row, or one item.

    Two lines are in the same group when they overlap horizontally (same cell, wrapped onto the
    next row) or when one of them continues the other across a line break - a hyphen at the end of
    one and a lowercase start on the next (`_hyphen_parents`). A continuation may be seen before
    the line it continues, because lines are walked left to right; it then waits for that line and
    joins its group, and no unrelated line joins a group that is waiting.
    """
    parents = _hyphen_parents(lines)
    groups: list[list[Line]] = []
    waiting: dict[int, list[Line]] = {}  # id(line) -> lines that continue it

    def place(line: Line, group: list[Line]) -> None:
        group.append(line)
        for follower in waiting.pop(id(line), ()):
            place(follower, group)

    def placed(line: Line) -> bool:
        return any(other is line for group in groups for other in group)

    for line in sorted(lines, key=lambda ln: ln.bbox.x0):
        if placed(line):
            continue  # came in as a continuation of a line before it
        parent = parents.get(id(line))
        if parent is not None and not any(other is line for group in waiting.values() for other in group):
            waiting.setdefault(id(parent), []).append(line)
            continue  # it joins the line it continues, when that line comes round
        group = None
        for candidate in groups:
            if parent is not None:
                if any(other is parent for other in candidate):
                    group = candidate
                    break
            elif any(
                _x_overlap_ratio(line.bbox, other.bbox) >= tunables.get(_CELL_OVERLAP_KEY)
                for other in candidate
            ):
                group = candidate
                break
        if group is None:
            group = []
            groups.append(group)
        place(line, group)
    groups.extend(waiting.values())  # a line whose continuation never came round
    return groups


def _split_side_by_side_lines(blocks: list[Block]) -> list[Block]:
    """Split a block whose lines sit beside each other into one block per cell.

    MuPDF groups by proximity, so a table's header row - three short lines on one baseline -
    arrives as a single block. Read as a paragraph it becomes "Plate Cycles Deflection", and
    the translation of all three is written into the first cell's box.

    A line that continues the one above it across a line break is not a cell of its own, and is
    not a cell of anything else either: arXiv 2507.03009's footer holds a footnote and a URL set
    around it, and the URL's second row - `reference/chat/create`, whose hyphen the join above
    refused because a URL's hyphen is part of the link - overlaps the footnote's column, so it was
    grouped with the footnote and translated as `1See: reference/chat/create`. A line beginning
    lowercase under a line ending in a hyphen belongs to that line, whatever the columns say.

    Lines are walked left to right, as they always were - a note's marker and the text beside it
    belong together, and reading order split `Note.` off the note body it belongs to. A
    continuation seen before the line it continues waits for it and joins its group when the line
    above comes round; no unrelated line joins a group that is waiting.
    """
    out: list[Block] = []
    for block in blocks:
        if len(block.lines) < 2:
            out.append(block)
            continue

        groups = _cell_groups(block.lines)

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


def _table_grid(blocks: list[Block]) -> dict[str, tuple[int, int, int]]:
    """(table_id, row, col) for every block that sits in a table grid, keyed by block id.

    A row of cells and a line of a paragraph look alike to a merger that only asks about font
    size, vertical gap and horizontal overlap. What tells them apart is repetition: cells line
    up into columns across consecutive rows, and a paragraph has no columns to line up with.

    Which table a row belongs to is found by chaining that relation transitively (row 1 lines up
    with row 2, row 2 lines up with row 3 -> rows 1-3 are one table) via union-find over row
    indices, rather than only ever comparing a row to its immediate neighbour - the middle row of
    a three-row table is what every other row matches against, and a purely pairwise scan without
    the union step would still find the table, but two tables placed close enough that their
    outer rows also pass the alignment test would merge into one.
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
    if not candidates:
        return {}

    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # Which cell ids each row actually matched - a row can have a cell that lines up with
    # nothing in any other row (a caption sharing the row's band, say), and that one cell stays
    # out of the table while its row-mates go in.
    row_matches: dict[int, set[str]] = {i: set() for i in range(len(candidates))}
    for index, row in enumerate(candidates):
        height = max(b.bbox.height for b in row) or 1.0
        for j, other in enumerate(candidates[index + 1 :], start=index + 1):
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
                union(index, j)
                row_matches[index].update(a.id for a, _ in matched)
                row_matches[j].update(b.id for _, b in matched)

    components: dict[int, list[int]] = {}
    for i in range(len(candidates)):
        if row_matches[i]:
            components.setdefault(find(i), []).append(i)

    result: dict[str, tuple[int, int, int]] = {}
    for table_id, row_indices in enumerate(components.values()):
        row_indices.sort(key=lambda i: candidates[i][0].bbox.y0)
        cell_ids = {cid for i in row_indices for cid in row_matches[i]}
        table_cells = [b for i in row_indices for b in candidates[i] if b.id in cell_ids]
        height = max(b.bbox.height for b in table_cells) or 1.0

        # Columns: cluster every matched cell's x0 across the whole table into buckets, in
        # left-to-right order, so a cell's column index is consistent across every row even when
        # a row is missing a cell (a merged header, a short last row).
        columns: list[float] = []
        col_of: dict[str, int] = {}
        for cell in sorted(table_cells, key=lambda b: b.bbox.x0):
            for col_index, x0 in enumerate(columns):
                if abs(cell.bbox.x0 - x0) <= height * tunables.get(_COLUMN_ALIGN_KEY):
                    col_of[cell.id] = col_index
                    break
            else:
                col_of[cell.id] = len(columns)
                columns.append(cell.bbox.x0)

        for row_position, i in enumerate(row_indices):
            for cell in candidates[i]:
                if cell.id in cell_ids:
                    result[cell.id] = (table_id, row_position, col_of[cell.id])

    return result


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
    grid_positions = _table_grid(blocks)
    in_grid = set(grid_positions)

    remaining = sorted(blocks, key=lambda b: b.bbox.y0)
    merged: list[Block] = []
    while remaining:
        current = remaining.pop(0)
        if current.id in in_grid:
            table_id, row, col = grid_positions[current.id]
            current.role = BlockRole.TABLE
            current.table_id = table_id
            current.table_row = row
            current.table_col = col
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
                # Two lines that are each centred make a centred block. Leaving this out reset
                # every merged block to "left" - a cover title of two centred lines was drawn
                # flush left.
                align=current.align if current.align == candidate.align else "left",
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
