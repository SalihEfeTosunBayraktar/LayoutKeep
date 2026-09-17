"""Image reader: turns a scanned page (a raster image) into a DocIR Document via OCR.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-ocr.md):
  - `ocr.engine.OcrEngine` finds text boxes with a real per-box confidence.
  - Boxes are merged into lines (already mostly true of rapidocr's own detections, but boxes
    split by a mid-line obstruction are re-joined here), then lines into paragraphs by vertical
    gap and left-alignment, mirroring the paragraph grouping `pdf_reader.py` gets for free from
    pymupdf.
  - Reading order is simple top-to-bottom, left-to-right: scanned pages in this phase are not
    given multi-column layout detection (unlike `pdf_reader.py`) because nothing in the Phase 2
    scope calls for it yet; `Block.order` is still filled for real, just via a simpler rule.
  - Text/background colour per block comes from a 2-means split of the block's own pixels.
  - Bold/italic detection is deliberately not attempted (see lk-ocr.md): a wrong guess is worse
    than no guess, so `Style.bold`/`Style.italic` stay at their DocIR defaults (False).

This module must not `import pymupdf` (CONTRACT.md S4 reserves that to the two PDF modules).
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import numpy as np
from PIL import Image

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Direction,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.ocr.engine import OcrEngine, RapidOcrEngine, TextBox
from layoutkeep.ocr.layout_detector import (
    LABEL_TO_ROLE,
    NOT_A_PARAGRAPH,
    LayoutDetector,
    LayoutRegion,
    resolve_duplicates,
)
from layoutkeep.ocr.layout_vlm import ChatFn, classify
from layoutkeep.readers._layout import infer_alignment, join_hyphenation
from layoutkeep.readers._segment import segment

#: Below this OCR confidence, the containing block is flagged for human review.
NEEDS_REVIEW_THRESHOLD = 0.80
#: Assumed image resolution when the file carries no DPI metadata (PIL default for PNG/JPEG
#: created by screenshot/scan tools without an explicit resolution tag).
_DEFAULT_DPI = 96.0
#: Characters per 1000 square points, below which a page's text layer is not a text layer and
#: the page has to be read by OCR.
#:
#: This was an absolute count of ten characters, which assumes something about page size and
#: about what a text layer contains. Both assumptions broke on the second document tried:
#: `Notes_260730_153127.pdf` is 22 A4 pages, each an image with a thirteen-character template
#: stamp in its text layer - "my notes / date". Thirteen is not under ten, so every page was
#: read as though it had text, OCR never ran, and the content of every page was silently
#: ignored - 96 characters recovered from the whole document, where OCR reads 362 off page 2
#: alone.
#:
#: Density separates the cases by three orders of magnitude, and scales with the page instead of
#: assuming its size:
#:
#:     book, 318x424pt, no text layer         0.00 chars / 1000pt2
#:     notes, A4, template stamp only         0.03
#:     a real text layer (our own output)    11.16 - 21.38
#:
#: So the threshold sits between them with room to spare, where ten characters sat three away
#: from a stamp.
_SCANNED_TEXT_DENSITY = 1.0

#: How much of the page a picture must cover before OCR has anything worth reading.
#:
#: Measured on the two documents in hand: the textbook's pages are one full-page image (100%),
#: and the notes document's pages carry one image covering 8% to 61%. So the floor sits under
#: the smallest real case. It exists because text density alone is not a scan test - a small
#: born-digital page with a caption and no picture reads as "negligible text" too, and OCR would
#: then invent a second copy of everything on it.
_SCANNED_IMAGE_COVERAGE = 0.05

#: What a detected text box's height means, relative to the type size of the text in it.
#:
#: It is tempting to read the box height AS the font size - it was, and it is wrong. A detector
#: box wraps the whole line band, not the em: measured over 19 multi-line blocks of
#: `computer-systems-Architecture.pdf`, consecutive boxes sit only 0.957 box-heights apart, so
#: the boxes actually overlap and the height is the *line pitch*, not the size. Writers stack
#: lines at 1.2x the font size (`pdf_writer._LINE_HEIGHT_RATIO`), so treating the pitch as the
#: size made every redrawn line ~1.2x taller than the one it replaced and paragraphs no longer
#: fitted the boxes they came from: 120 of 210 blocks on a six-page scan were flagged
#: overflowing. 0.957 / 1.2 is the factor that puts the redrawn pitch back on the scanned one.
#:
#: Named in two parts so the relationship stays visible: the measured ratio, and the line-height
#: the writers actually stack lines at (`pdf_writer._LINE_HEIGHT_RATIO` / `image_writer`). The
#: same line height decides how much blank paper one more line needs (`_grant_blank_paper`), so
#: it must be the one number, not two that drift apart.
_PITCH_TO_BOX_HEIGHT = 0.957

#: The tunable that holds how tall a rendered line is, relative to the font size. One number,
#: read by the reader (to derive a size and to measure blank paper) and by the writer (to stack
#: the lines). It was declared separately in three places, all 1.2, with nothing tying them
#: together - and if they drift, every scanned page comes out mis-sized. Readers and writers may
#: not import each other (CONTRACT.md D1), so the shared value lives where both may read it.
#:
#: The key says "merge" because that is what first needed it; its meaning is broader now.
_LINE_HEIGHT_KEY = "merge.line_height_ratio"


def line_height_ratio() -> float:
    """How tall a rendered line is, as a multiple of the font size.

    Read at use, never captured at import: a module constant computed from a tunable is
    evaluated once when the module loads, so a setting changed afterwards would never be seen.
    """
    return tunables.get(_LINE_HEIGHT_KEY)


def box_height_to_font_size() -> float:
    """What to multiply a detector's box height by to get a type size.

    Only holds while the line height it assumes is the one the writer stacks lines at, which is
    why both read `_LINE_HEIGHT_KEY` rather than each keeping a copy.
    """
    return _PITCH_TO_BOX_HEIGHT / line_height_ratio()


def is_scanned_page(
    extracted_text: str, page_area_pt2: float, image_coverage: float = 1.0
) -> bool:
    """True when a page's text has to come from OCR because the page itself is a picture.

    Two things have to hold, and the conjunction matters. The text layer must be negligible FOR
    A PAGE OF THAT SIZE - see `_SCANNED_TEXT_DENSITY` - and there must be enough image on the
    page for OCR to have something to read.

    Density alone is not enough: a small page with a little text and no picture on it is a page
    with a text layer, not a scan, and OCR would invent a second copy of everything. Nine tests
    of the born-digital path said so the moment density went in on its own.

    Takes plain values rather than a pymupdf page so this module stays free of a pymupdf import
    (CONTRACT.md). `image_coverage` is the share of the page covered by pictures, 0.0 to 1.0; it
    defaults to 1.0 so a caller that only has the text - the existing unit tests, a reader with
    no picture information - still gets the density answer on its own.
    """
    characters = len(extracted_text.strip())
    if image_coverage < _SCANNED_IMAGE_COVERAGE:
        return False
    if page_area_pt2 <= 0:
        return characters == 0
    return characters / (page_area_pt2 / 1000.0) < _SCANNED_TEXT_DENSITY


def read_image(path: str | Path, *, engine: OcrEngine | None = None) -> Document:
    """Read a single image file into a one-page DocIR Document."""
    image = Image.open(path).convert("RGB")
    page = _page_from_image(image, number=1, source_ref=str(path), engine=engine)
    doc = Document(source_path=str(path), source_format="image")
    doc.pages = [page]
    return doc


#: Share of a page's blocks that may sit below the review threshold before the page is treated
#: as badly read and worth a second, higher-resolution pass.
#:
#: Measured over nine pages of `computer-systems-Architecture.pdf` at 200 DPI: the share runs
#: 0.0-4.7% on the seven that read cleanly, and 12.0% and 11.2% on the two that did not. The
#: threshold sits in that gap. Page 54 is the case it exists for - a pristine 600-DPI scan of
#: "Simplify the following expressions in (1) sum-of-products" that came out as
#: "Sin os -ns ( s ms o ong", and reads correctly at 300.
#:
#: Raising the resolution for every page instead would pay 2.25x the pixels for +1.5%
#: characters and +0.006 mean confidence across those nine, and OCR is the CPU-bound half of a
#: run - so the cost goes where the cheap pass actually failed.
_RETRY_LOWCONF_SHARE = 0.08


def expected_characters(page: Page) -> float:
    """How much text a pass recovered that we believe: characters weighted by confidence.

    Used to pick between two OCR passes rather than to assume the higher resolution won - page
    61 of this book reads a line correctly at 200 DPI and garbles it at 300, so more pixels is
    not automatically better and the reader measures instead.

    Mean confidence was the wrong measure and the disagreement is real, not theoretical: a
    recogniser that drops a hard line scores higher on what is left, so "surer" and "read more"
    part company. On page 451 of the book, 200 DPI reads 1746 characters at 0.954 and 300 DPI
    reads 1681 at 0.977 - confidence chooses the pass that lost 65 characters. Weighting the
    characters by the confidence in them picks correctly there and on the four other pages
    measured across both documents.
    """
    return sum(len(b.text) * b.confidence for b in page.blocks)


def needs_higher_resolution(page: Page) -> bool:
    """True when enough of the page's blocks are doubtful that it is worth rendering again.

    An empty page is not a failed read - it is a plate or a blank leaf, and re-rendering it
    would find nothing twice.
    """
    if not page.blocks:
        return False
    doubtful = sum(1 for b in page.blocks if b.confidence < NEEDS_REVIEW_THRESHOLD)
    return doubtful / len(page.blocks) > _RETRY_LOWCONF_SHARE


def _apply_region_verdicts(page: Page, image: Image.Image, classifier: ChatFn) -> None:
    """Let a vision model say what each block is, and stop a tall box dictating a large font.

    Role first: telling a heading from a displayed formula from a running header is the one
    judgement that has no signal in the geometry. Everything here used to be decided from the
    height of the detected box, so an equation with a sigma in it was promoted to a heading and
    redrawn half again as large - text that grew for no reason.

    Then size. A block the model calls `same` or `smaller` than the page's body text keeps the
    page's median size however tall its own box happens to be, which is what a folio sharing a
    line with the running header did to it (9.57pt against a 6.3pt page).

    Blocks are the unit asked about rather than detected lines: a block is what carries a role
    and a size, so the answers map onto them one for one, and there are fewer of them to list.
    """
    blocks = page.blocks
    if not blocks:
        return
    boxes = [(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1) for b in blocks]
    verdicts = classify(image, boxes, [b.text for b in blocks], classifier)
    if not verdicts:
        return

    sizes = [b.dominant_style().size for b in blocks if b.dominant_style().size > 0]
    body_size = statistics.median(sizes) if sizes else 0.0

    for index, block in enumerate(blocks, start=1):
        verdict = verdicts.get(index)
        if verdict is None:
            continue
        block.role = verdict.role
        if verdict.size != "larger" and body_size > 0:
            for line in block.lines:
                for span in line.spans:
                    if span.style.size > body_size:
                        span.style.size = body_size


def page_from_rendered_page(
    image: Image.Image,
    *,
    number: int,
    source_ref: str,
    dpi: float,
    width_pt: float,
    height_pt: float,
    engine: OcrEngine | None = None,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
) -> Page:
    """OCR one rendered page of a scanned document and return it in PDF points.

    `pdf_reader.py` owns the pymupdf import (CONTRACT.md), so it rasterises the page and hands
    the pixels here. Everything OCR produces is in those render pixels; the rest of the pipeline
    - every writer, and the whole fitting pass - measures in points, so the conversion happens
    once, here, rather than being re-derived (and eventually got wrong) downstream.

    `dpi` is written onto the image before recognition so `_block_from_paragraph` derives font
    sizes from the real render resolution instead of the PIL default of 96, which would inflate
    every size and overflow the refitted boxes.
    """
    image.info["dpi"] = (dpi, dpi)
    page = _page_from_image(
        image, number=number, source_ref=source_ref, engine=engine, layout=layout
    )
    _grant_blank_paper(page, np.array(image.convert("L")), dpi=dpi)

    if classifier is not None:
        _apply_region_verdicts(page, image, classifier)

    scale = 72.0 / dpi
    for block in page.blocks:
        block.bbox = _scaled(block.bbox, scale)
        for line in block.lines:
            if line.bbox is not None:
                line.bbox = _scaled(line.bbox, scale)
            for span in line.spans:
                span.bbox = _scaled(span.bbox, scale)

    page.width, page.height = width_pt, height_pt

    # Alignment, inferred the same way `pdf_reader` infers it for a page that has a text layer.
    # Nothing set it here before, so every block OCR produced defaulted to "left" and each
    # centred line on a scan - a chapter title, a figure caption - was redrawn hard against the
    # left margin. Computed after the conversion above so the box and the page width are both
    # in points.
    for block in page.blocks:
        block.align = infer_alignment(
            block.bbox, page.width, [line.bbox for line in block.lines if line.bbox is not None]
        )

    return page


def _scaled(bbox: BBox, scale: float) -> BBox:
    return BBox(bbox.x0 * scale, bbox.y0 * scale, bbox.x1 * scale, bbox.y1 * scale)


#: How many extra rendered lines of blank paper a block may take below itself.
#:
#: Turkish runs longer than English, so a paragraph that filled its box in the source needs
#: another line once translated. `fitting/` can only shrink the type to a readability floor or
#: ask for a shorter rendering; when neither is enough the block is reported as overflowing - 17
#: of 193 blocks on six pages of `computer-systems-Architecture.pdf`. One extra line is what
#: those 17 were short of, and on a scanned page the space between paragraphs is usually blank
#: paper: measured over 38 prose blocks there, the median gap below a block is 13.2pt and 26 of
#: the 38 have room for a line.
#:
#: One line, and no more - taking the whole gap would close up the paragraph spacing and change
#: the page.
_BLANK_PAPER_LINES = 1

#: How much darker than the paper a pixel has to be to count as ink. Generous, because the point
#: is to notice a figure's edge or a rule, not to resolve faint scanner speckle.
_INK_MARGIN = 40


def _grant_blank_paper(page: Page, grey: np.ndarray, *, dpi: float) -> None:
    """Extend each block downward over paper that is provably blank, up to one line pitch.

    Bounded by the pixels rather than by the next block on purpose. A figure that OCR found no
    text in is not a block, so a "grow until the next block" rule would let a paragraph above it
    grow across the figure - and `pdf_writer._cover_scanned_blocks` would then paint the figure
    out while clearing the source text under that box. That is the same class of damage
    `_LINE_JOIN_GAP_RATIO` exists to prevent, so the growth stops at the first row with ink in
    it.

    Runs before the geometry is converted, so boxes are still in image pixels while `Style.size`
    is already in points - hence `dpi`, to bring the line height into the same space as the box
    it is compared against.
    """
    if grey.size == 0:
        return
    height, width = grey.shape
    paper = float(np.median(grey))
    ink_below = paper - _INK_MARGIN
    px_per_point = dpi / 72.0

    for block in page.blocks:
        # The height one rendered line occupies, by the same rule the writer will use. Measuring
        # the scan's own pitch instead looks more faithful but leaves the block a fraction short
        # of the line it is being grown for, because the two differ slightly.
        line_height = block.dominant_style().size * line_height_ratio() * px_per_point
        if line_height <= 0:
            continue
        x0 = max(0, int(block.bbox.x0))
        x1 = min(width, int(block.bbox.x1) + 1)
        if x1 <= x0:
            continue
        # A detector box ends at the last line's glyphs, so a block holding N lines is
        # (N-1) pitches plus one box height - short of the N pitches the writer stacks them at.
        # Asking for "one more pitch" therefore lands a line short; ask for the height that
        # actually holds one more rendered line.
        wanted = (len(block.lines) + _BLANK_PAPER_LINES) * line_height - block.bbox.height
        if wanted <= 0:
            continue
        # Row indices are integers and the box edge is not, so the bounds are taken outward and
        # the *result* is the float the caller asked for. Truncating instead loses up to a pixel
        # at each end, which was enough to land the block a fraction under the line it needed.
        first_row = min(height, max(0, math.floor(block.bbox.y1) + 1))
        last_row = min(height, math.ceil(block.bbox.y1 + wanted))
        if last_row <= first_row:
            continue

        strip = grey[first_row:last_row, x0:x1]
        dark = np.where((strip < ink_below).any(axis=1))[0]
        if len(dark):
            # Stop one row above the ink, so nothing that is drawn on the page is claimed.
            bottom = max(block.bbox.y1, float(first_row + int(dark[0]) - 1))
        else:
            bottom = block.bbox.y1 + wanted
        if bottom > block.bbox.y1:
            block.bbox = BBox(block.bbox.x0, block.bbox.y0, block.bbox.x1, bottom)


def _page_from_image(
    image: Image.Image,
    *,
    number: int,
    source_ref: str,
    engine: OcrEngine | None = None,
    layout: LayoutDetector | None = None,
) -> Page:
    engine_ = engine if engine is not None else RapidOcrEngine()
    boxes = engine_.recognize(image)
    dpi = float(image.info.get("dpi", (_DEFAULT_DPI, _DEFAULT_DPI))[0]) or _DEFAULT_DPI

    pixels = np.array(image)
    regions = resolve_duplicates(layout.detect(image)) if layout is not None else []
    # Words are joined into lines within one region only. The model's regions are the columns: on a
    # magazine page with a narrow gutter, words of both columns at the same height were joined into
    # one line, so a translation mixed two paragraphs and was drawn over both columns.
    lines = _lines_within_regions(boxes, regions) if regions else _merge_boxes_into_lines(boxes)

    # A layout model, when installed, says where each paragraph, heading and caption is; its
    # text regions become blocks directly, with the role it assigned. Lines it places in a
    # picture or a table are labels and cells, one block each. Lines it places nowhere fall
    # through to the geometric grouping below, so a page is never read worse for having it.
    groups: list[tuple[list[list[TextBox]], BlockRole | None]] = []
    rest = lines
    if layout is not None:
        claimed, labels, rest = _lines_by_region(lines, regions)
        # A table cell or a figure label is never a paragraph. Grouping them geometrically, as
        # they were, took them away from the page they belong to: among a table's lines alone
        # the table's own column became the "body column", and its rows were merged into one
        # block - book page 451's function table came back as "Veri yolu durumu Yuksek
        # empedansli Yuksek empedansli ...".
        for label, line in labels:
            # Text inside a picture is part of the picture and stays as scanned: re-typesetting a
            # circuit diagram's labels (book page 61) squeezed translations between its wires and
            # redrew subscripts as "D{2}". A table's cells are text laid out in a grid, and are
            # translated one cell at a time.
            groups.append(([line], BlockRole.FIGURE if label == "picture" else BlockRole.TABLE))
        page_line_height = _median_line_height(lines)
        for label, region_lines in claimed:
            role = LABEL_TO_ROLE.get(label, BlockRole.BODY)
            # The model's box is an upper bound, not the answer: on one fixture it boxed margin
            # keywords together with the paragraph beside them. The page's own whitespace still
            # separates those, and a region that is really one paragraph has no gap to cut.
            groups.extend(
                (part.lines, role)
                for part in segment(region_lines, line_height=page_line_height)
            )

    # The rest is cut into regions by the page's own whitespace first, and paragraphs are
    # grouped inside each one. Grouping across the whole page at once means the body column, the
    # line pitch and the indent are single numbers, and a page with two columns has two of each
    # - which is how a two-column scan came back with eight of sixteen blocks starting
    # mid-sentence. See `readers/_segment.py` for what that cost in per-line rules first.
    for region in segment(rest):
        groups.extend((para, None) for para in _merge_lines_into_paragraphs(region.lines))

    blocks: list[Block] = []
    from_text_regions: list[Block] = []
    for i, (para, role) in enumerate(groups):
        block = _block_from_paragraph(para, pixels, dpi, index=i, page_index=number - 1)
        if role is not None:
            block.role = role
            from_text_regions.append(block)
        blocks.append(block)

    if layout is not None:
        _cap_sizes_by_role(blocks, measured_from=from_text_regions)
        blocks = _in_reading_order(blocks, lines)
    for i, block in enumerate(blocks):
        block.order = i

    return Page(
        number=number,
        width=float(image.width),
        height=float(image.height),
        blocks=blocks,
        source_ref=source_ref,
    )


def _median_line_height(lines: list[list[TextBox]]) -> float:
    heights = [max(b.bbox[3] for b in line) - min(b.bbox[1] for b in line) for line in lines]
    return statistics.median(heights) if heights else 1.0


def _lines_within_regions(boxes: list[TextBox], regions: list[LayoutRegion]) -> list[list[TextBox]]:
    """Join words into lines separately inside each region, and among the words in no region."""
    groups: dict[int, list[TextBox]] = {}
    for box in boxes:
        x0, y0, x1, y1 = box.bbox
        area = max((x1 - x0) * (y1 - y0), 1e-6)
        best, best_area = -1, float("inf")
        for index, region in enumerate(regions):
            rx0, ry0, rx1, ry1 = region.bbox
            overlap = max(0.0, min(x1, rx1) - max(x0, rx0)) * max(0.0, min(y1, ry1) - max(y0, ry0))
            size = (rx1 - rx0) * (ry1 - ry0)
            if overlap / area >= _REGION_MEMBERSHIP and size < best_area:
                best, best_area = index, size
        groups.setdefault(best, []).append(box)
    lines: list[list[TextBox]] = []
    for group in groups.values():
        lines.extend(_merge_boxes_into_lines(group))
    return lines


#: How much of a line has to lie inside a detected region to belong to it.
_REGION_MEMBERSHIP = 0.5


def _lines_by_region(
    lines: list[list[TextBox]], regions: list[LayoutRegion]
) -> tuple[
    list[tuple[str, list[list[TextBox]]]],
    list[tuple[str, list[TextBox]]],
    list[list[TextBox]],
]:
    """Put each line in the detected region holding most of it.

    Returns the text regions with their lines, top to bottom; the lines inside regions that are
    not prose (`NOT_A_PARAGRAPH` - figure labels, table cells); and the lines in no region.
    """
    members: dict[int, list[list[TextBox]]] = {}
    labels: list[tuple[str, list[TextBox]]] = []
    rest: list[list[TextBox]] = []
    for line in lines:
        x0 = min(b.bbox[0] for b in line)
        y0 = min(b.bbox[1] for b in line)
        x1 = max(b.bbox[2] for b in line)
        y1 = max(b.bbox[3] for b in line)
        area = max((x1 - x0) * (y1 - y0), 1e-6)
        # Of the regions holding enough of the line, the smallest wins: a heading or a caption
        # can sit inside a figure's box, and the tighter box is the one that describes the line.
        best, best_area = -1, float("inf")
        for index, region in enumerate(regions):
            rx0, ry0, rx1, ry1 = region.bbox
            overlap = max(0.0, min(x1, rx1) - max(x0, rx0)) * max(0.0, min(y1, ry1) - max(y0, ry0))
            region_area = (rx1 - rx0) * (ry1 - ry0)
            if overlap / area >= _REGION_MEMBERSHIP and region_area < best_area:
                best, best_area = index, region_area
        if best < 0:
            rest.append(line)
        elif regions[best].label in NOT_A_PARAGRAPH:
            labels.append((regions[best].label, line))
        else:
            members.setdefault(best, []).append(line)

    claimed = [
        (regions[index].label, sorted(found, key=lambda line: min(b.bbox[1] for b in line)))
        for index, found in members.items()
    ]
    return claimed, labels, rest


#: Roles allowed to be set larger than the page's body text.
_MAY_BE_LARGER = frozenset({BlockRole.TITLE, BlockRole.HEADING})

#: Roles set in the page's running text size, which is what the ceiling is measured from. List
#: items are included because an exercise page is nothing but list items: page 54 of the book
#: has no `text` region at all, so a ceiling measured off BODY alone left its running header at
#: 9.57pt against 6.5pt type.
_RUNNING_TEXT = frozenset({BlockRole.BODY, BlockRole.LIST})


def _cap_sizes_by_role(blocks: list[Block], *, measured_from: list[Block]) -> None:
    """Stop a tall box making text that is not a heading larger than the body.

    The size of an OCR'd span comes from its box height, and a box grows for reasons that have
    nothing to do with type size: a sigma in an equation, a large folio beside a running header.
    That was the "text that grew for no reason" of the one-to-one comparison. The model now says
    which blocks are headings, so only those may exceed the body size.
    """
    # The ceiling is the median of each running-text BLOCK's own median size, not the median over
    # every word box. Half of all word boxes sit above their median by definition, so capping
    # there shrank ordinary body text - page 451's paragraphs from 6.60pt to 6.32pt, visibly
    # smaller than the source once translated. A block's median is its type size; the page's
    # median of those is the body size, and only what exceeds it is an outlier.
    #
    # Measured only over blocks the model placed in a text region. Table cells and figure labels
    # are blocks too, in small type and in numbers: counted as body they outvoted the paragraphs
    # and page 451 still came out at 6.03pt against 6.60pt after the median was fixed.
    body = [
        statistics.median(sizes)
        for block in measured_from
        if block.role in _RUNNING_TEXT
        and (sizes := [s.style.size for line in block.lines for s in line.spans if s.style.size > 0])
    ]
    if not body:
        return
    ceiling = statistics.median(body)
    for block in blocks:
        if block.role in _MAY_BE_LARGER:
            continue
        for line in block.lines:
            for span in line.spans:
                span.style.size = min(span.style.size, ceiling)


def _in_reading_order(blocks: list[Block], lines: list[list[TextBox]]) -> list[Block]:
    """Order blocks by the same whitespace cuts that order lines.

    The model gives regions but no order - Docling itself orders them with rules - and the blocks
    here come from two sources, so they are cut as one set. Each block stands in as one box, and
    the gap threshold stays the page's own line height rather than one measured off whole blocks.
    """
    if len(blocks) < 2:
        return blocks
    line_height = _median_line_height(lines)
    stand_ins = [
        [TextBox(text=str(i), bbox=(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1), confidence=1.0)]
        for i, b in enumerate(blocks)
    ]
    regions = segment(stand_ins, line_height=line_height)
    return [blocks[int(line[0].text)] for region in regions for line in region.lines]


# --------------------------------------------------------------------------------------
# Boxes -> lines -> paragraphs
# --------------------------------------------------------------------------------------


#: How far apart two boxes in the same y-band may sit and still count as one interrupted line,
#: as a multiple of their height. Measured on page 61 of `computer-systems-Architecture.pdf`:
#: the one genuine join there ('46' + the running header) has a gap of 0.79x, while the figure's
#: label columns - which must not be joined - are 2.79x apart and worse. Vertical overlap alone
#: welded them into single lines whose bbox spanned the whole figure.
_LINE_JOIN_GAP_RATIO = 1.5


def _merge_boxes_into_lines(boxes: list[TextBox]) -> list[list[TextBox]]:
    """Group boxes whose vertical spans overlap into one line, left-to-right.

    rapidocr already detects whole text lines, so most groups end up with a single box; this
    only kicks in when a line got split into two boxes (e.g. an obstruction mid-line). Sharing a
    y-band is necessary but not sufficient - two boxes far apart horizontally are separate
    things that happen to sit at the same height, not one line, so `_LINE_JOIN_GAP_RATIO` caps
    how far the join will reach.
    """
    remaining = sorted(boxes, key=lambda b: b.bbox[1])
    lines: list[list[TextBox]] = []
    for box in remaining:
        y0, y1 = box.bbox[1], box.bbox[3]
        mid = (y0 + y1) / 2
        placed = False
        for line in lines:
            line_y0 = min(b.bbox[1] for b in line)
            line_y1 = max(b.bbox[3] for b in line)
            if line_y0 <= mid <= line_y1 and _within_join_reach(line, box):
                line.append(box)
                placed = True
                break
        if not placed:
            lines.append([box])
    for line in lines:
        line.sort(key=lambda b: b.bbox[0])
    lines.sort(key=lambda line: min(b.bbox[1] for b in line))
    return lines


def _within_join_reach(line: list[TextBox], box: TextBox) -> bool:
    """True when `box` is close enough to `line` to be a continuation of it rather than a
    separate piece of text that merely shares its height."""
    line_x0 = min(b.bbox[0] for b in line)
    line_x1 = max(b.bbox[2] for b in line)
    # Negative when the boxes overlap horizontally, which is always a join.
    gap = max(line_x0 - box.bbox[2], box.bbox[0] - line_x1)
    heights = [b.bbox[3] - b.bbox[1] for b in (*line, box)]
    height = sum(heights) / len(heights)
    return gap <= height * _LINE_JOIN_GAP_RATIO


#: How far right of the line above a line must start to read as a new, indented paragraph, as a
#: multiple of the line height.
#:
#: And how far LEFT it may start and still be the same paragraph (`_DEINDENT_LIMIT`). Grouping
#: used `abs()` on the difference with a single 1.5 tolerance, which in a book that indents its
#: first lines splits every paragraph: measured on page 22 of
#: `computer-systems-Architecture.pdf`, the opening line sits at x=90.0 and the body at x=73.5 -
#: a 16.6pt indent against an 8pt line height, so 2.1 heights, over the tolerance. Each
#: paragraph became two blocks, an indented one-liner and the rest, and 6 of that page's 18
#: blocks began mid-sentence: unable to be translated, fitted to different type sizes (6.60pt
#: against 8.04pt on the same paragraph), and colliding because they were fitted apart.
#:
#: The de-indent limit is what still separates a centred caption from the paragraph beneath it -
#: that step left is much larger than an indent.
_NEW_PARAGRAPH_INDENT = 0.5
_DEINDENT_LIMIT = 3.0
#: Vertical gap, in line heights, still close enough to be the next line of a paragraph.
_LINE_GAP_RATIO = 0.6


#: How wide a line must be, against the page's widest, to count as body text when locating the
#: body column.
#:
#: The column used to be the median left edge over every line, which works on a page of prose
#: and fails on anything else: figure labels, grid cells and table entries sit scattered to the
#: right and drag the median with them. Measured at 200 DPI against a body column at 205px, the
#: median landed at 308 on page 28 and 377 on page 121, so real body lines were each mistaken
#: for a margin note and every line of every paragraph came back as its own block - 17 and 14
#: blocks beginning mid-sentence on those two pages alone.
#:
#: Body lines are long and labels are short. Half of the page's own widest line separates them
#: on every page type measured - figure-heavy, table-heavy, prose, and hanging-indent exercise
#: lists - without needing to know anything about the book.
_BODY_LINE_SHARE = 0.5


def _body_column(lines: list[list[TextBox]]) -> float:
    """Where this page's body text starts: the median left edge among its long lines."""
    spans = [
        (
            min(b.bbox[0] for b in line),
            max(b.bbox[2] for b in line) - min(b.bbox[0] for b in line),
        )
        for line in lines
    ]
    widest = max(width for _x0, width in spans)
    long_lefts = [x0 for x0, width in spans if width >= widest * _BODY_LINE_SHARE]
    # A page with no long lines at all - a table of contents, an index - has its widest line as
    # the reference, so this cannot come back empty.
    return statistics.median(long_lefts or [x0 for x0, _w in spans])


def _merge_lines_into_paragraphs(lines: list[list[TextBox]]) -> list[list[list[TextBox]]]:
    """Group consecutive lines into paragraphs by vertical gap and left-alignment.

    Two things make this more than "compare each line with the one above".

    Indentation is asymmetric. A new paragraph announces itself by starting to the RIGHT of the
    line above; a line starting to the LEFT is the body of a paragraph whose first line was
    indented. Testing `abs()` against one tolerance split every paragraph in a book that indents
    (see `_NEW_PARAGRAPH_INDENT`).

    And a paragraph can be interrupted. This book prints a keyword in the left margin beside the
    paragraph it introduces - "OR", "inverter", "NAND" - level with the paragraph's body, so
    sorting lines top-to-bottom drops it between the indented opening line and the rest.
    Compared with the line above, the paragraph ended at the note. A line that far left of the
    page's body column is a different column: it becomes its own paragraph and leaves the one it
    interrupted open, so the line after it rejoins.

    The body column is the median left edge over all the lines - prose lines outnumber margin
    notes - rather than something measured from the neighbouring line, which cascades: once a
    centred caption is the thing being compared against, every body line under it looks like a
    different column too.
    """
    if not lines:
        return []

    body_x0 = _body_column(lines)

    paragraphs: list[list[list[TextBox]]] = [[lines[0]]]
    open_index = 0
    for cur in lines[1:]:
        anchor = paragraphs[open_index][-1]
        anchor_bottom = max(b.bbox[3] for b in anchor)
        anchor_height = (anchor_bottom - min(b.bbox[1] for b in anchor)) or 1.0
        anchor_x0 = min(b.bbox[0] for b in anchor)
        cur_top = min(b.bbox[1] for b in cur)
        cur_x0 = min(b.bbox[0] for b in cur)

        if body_x0 - cur_x0 > anchor_height * _DEINDENT_LIMIT:
            # A margin note: its own paragraph, and the interrupted one stays open.
            paragraphs.append([cur])
            continue

        indent = cur_x0 - anchor_x0
        close_enough = cur_top - anchor_bottom <= anchor_height * _LINE_GAP_RATIO
        aligned = (
            indent <= anchor_height * _NEW_PARAGRAPH_INDENT
            and -indent <= anchor_height * _DEINDENT_LIMIT
        )
        if close_enough and aligned:
            paragraphs[open_index].append(cur)
        else:
            paragraphs.append([cur])
            open_index = len(paragraphs) - 1
    return paragraphs


# --------------------------------------------------------------------------------------
# Paragraph -> Block, with colour detection
# --------------------------------------------------------------------------------------


def _block_from_paragraph(
    para: list[list[TextBox]], pixels: np.ndarray, dpi: float, *, index: int, page_index: int
) -> Block:
    doc_lines: list[Line] = []
    confidences: list[float] = []
    for line_boxes in para:
        spans: list[Span] = []
        line_bbox: BBox | None = None
        ordered = sorted(line_boxes, key=lambda box: box.bbox[0])
        for position, box in enumerate(ordered):
            # numpy float32 -> Python float: DocIR'in numpy taşımaması gerekir / DocIR must not carry numpy types
            x0, y0, x1, y1 = (float(c) for c in box.bbox)
            bbox = BBox(x0, y0, x1, y1)
            line_bbox = bbox if line_bbox is None else line_bbox.union(bbox)
            fg, bg = _box_colors(pixels, bbox)
            size_pt = float((y1 - y0) * 72.0 / dpi) * box_height_to_font_size()
            # "Arial" rather than the generic "sans-serif": fitting/fontmatch.py's classify()
            # checks its serif hint list before its sans hint list, and "serif" is a substring
            # of "sans-serif", so that literal string misclassifies as serif. "Arial" names a
            # real sans family and resolves correctly through the substitution table instead.
            style = Style(font_family="Arial", size=round(size_pt, 2), color=fg, background=bg)
            # Separate OCR boxes on one line are separated by a gap on the page, which is a space in
            # the text. A line's text joins its spans with nothing (right for a PDF text layer,
            # whose spans carry their own spaces), so without this every running header came out
            # as "46BOLUM IKI ..." - folio and title are two boxes.
            text = box.text if position == len(ordered) - 1 else f"{box.text.rstrip()} "
            spans.append(Span(text=text, bbox=bbox, style=style, direction=Direction.LTR))
            confidences.append(float(box.confidence))
        doc_lines.append(Line(spans=spans, bbox=line_bbox))

    # A word broken across a line break is put back together before anything downstream sees
    # it. Without this the second half becomes a segment of its own starting mid-word -
    # "tities in the table can be proven by..." - which no model can translate, so it came back
    # untranslated and the paragraph changed language at the hyphen.
    join_hyphenation(doc_lines)

    block_bbox = doc_lines[0].bbox
    for line in doc_lines[1:]:
        if line.bbox is not None:
            block_bbox = line.bbox if block_bbox is None else block_bbox.union(line.bbox)
    if block_bbox is None:
        block_bbox = BBox(0, 0, 0, 0)

    confidence = min(confidences) if confidences else 1.0
    return Block(
        id=f"img{page_index}#{index}",
        role=BlockRole.BODY,
        bbox=block_bbox,
        lines=doc_lines,
        direction=Direction.LTR,
        confidence=confidence,
        needs_review=confidence < tunables.get("ocr.needs_review_threshold"),
        review_reason=(
            f"OCR güveni düşük ({confidence:.2f})"
            if confidence < tunables.get("ocr.needs_review_threshold") else ""
        ),
    )


def _box_colors(pixels: np.ndarray, bbox: BBox) -> tuple[str, str | None]:
    """Foreground (text) and background colour of a box, via 2-means over its pixels.

    The smaller cluster is assumed to be the text - a text box, by construction, is mostly its
    own background with a minority of ink/glyph pixels.
    """
    x0, y0, x1, y1 = (max(0, int(bbox.x0)), max(0, int(bbox.y0)), int(bbox.x1), int(bbox.y1))
    crop = pixels[y0:y1, x0:x1]
    if crop.size == 0:
        return "#000000", None
    flat = crop.reshape(-1, 3).astype(np.float64)
    if len(flat) < 2:
        color = _to_hex(flat[0]) if len(flat) else "#000000"
        return color, None
    fg, bg = _kmeans2(flat)
    return _to_hex(fg), _to_hex(bg)


def _kmeans2(points: np.ndarray, *, iterations: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Plain 2-means over RGB points. Returns (minority-cluster centroid, majority-cluster
    centroid) i.e. (foreground, background). No sklearn dependency - this project targets a
    small install size and two clusters over a few thousand pixels needs no library."""
    lo = points[np.argmin(points.sum(axis=1))]
    hi = points[np.argmax(points.sum(axis=1))]
    centroids = np.stack([lo, hi])
    labels = None
    for _ in range(iterations):
        dist = np.linalg.norm(points[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(dist, axis=1)
        if labels is not None and np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for k in (0, 1):
            members = points[labels == k]
            if len(members):
                centroids[k] = np.median(members, axis=0)
    counts = np.bincount(labels, minlength=2)
    minority, majority = (0, 1) if counts[0] <= counts[1] else (1, 0)
    return centroids[minority], centroids[majority]


def _to_hex(rgb: np.ndarray) -> str:
    r, g, b = (round(c) for c in rgb[:3])
    r, g, b = (max(0, min(255, v)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"
