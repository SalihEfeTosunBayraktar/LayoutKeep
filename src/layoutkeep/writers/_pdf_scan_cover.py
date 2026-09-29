"""Covering the source text on a scanned page: paper colour, ink erasure, fill.

Taranmış sayfada kaynak metni örter: kâğıt rengi, mürekkep silme ve dolgu.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pymupdf

from layoutkeep.core.docir import Block
from layoutkeep.writers._pdf_redaction import is_wordless
from layoutkeep.writers._pdf_writer_common import _rect

if TYPE_CHECKING:  # numpy is imported where it is used: writing a PDF does not need it
    import numpy as np

#: How far outside its tight OCR box a block is painted over, in points. OCR reports the box of
#: the glyphs it recognised; ascenders, descenders and anti-aliased edges sit a fraction outside
#: it, and leaving that fringe behind puts a grey ghost of the source line under the
#: translation. Kept small - this paint is opaque, so every extra point is page content
#: destroyed for nothing.
_SCAN_COVER_PAD = 1.5


def _cover_scanned_blocks(
    page: pymupdf.Page, blocks: list[Block], *, keep: list[Block] = ()
) -> None:
    """Paint out the source text of a scanned page so the translation is not drawn over it.

    Redaction cannot do this: the words are pixels inside the page image, and `apply_redactions`
    is deliberately called with `PDF_REDACT_IMAGE_NONE` so that ordinary documents do not lose
    every figure that happens to touch a text block.

    Only the boxes OCR actually found are painted, so the rest of the scan - figures, rules,
    anything no block claimed - survives untouched. The fill is the block's own detected
    background rather than a hard white, so this works on a tinted or off-white scan too.

    Nothing that stays as scanned is painted into: a block in `keep` (not translated) or a
    wordless one keeps every pixel of its lines. Adjacent OCR lines overlap by about a point and
    the cover is padded, so without this the paint reached into the next line - book page 54's
    formula `b. AC' + B'D + ...` lost the top half of its glyphs to the line above it.
    """
    pad = (-_SCAN_COVER_PAD, -_SCAN_COVER_PAD, _SCAN_COVER_PAD, _SCAN_COVER_PAD)
    covered = [b for b in blocks if not is_wordless(b)]
    protected = [
        _rect(line.bbox)
        for block in [*keep, *(b for b in blocks if is_wordless(b))]
        for line in block.lines
        if line.bbox is not None
    ]
    cleared: list[tuple[pymupdf.Rect, Block]] = []
    for block in covered:
        rect = _rect(block.bbox) + pad
        for guard in protected:
            if not rect.intersects(guard):
                continue
            # Give way only to a neighbour: a protected line whose middle is below or above the
            # block's own box. One whose middle is inside it cannot be avoided by shrinking, and
            # shrinking would leave part of the source paragraph showing under its translation.
            middle = (guard.y0 + guard.y1) / 2
            if middle >= block.bbox.y1:
                rect.y1 = min(rect.y1, guard.y0)
            elif middle <= block.bbox.y0:
                rect.y0 = max(rect.y0, guard.y1)
        if rect.y1 > rect.y0:
            cleared.append((rect, block))

    if cleared and _erase_ink_from_scan(
        page, [(rect, block.dominant_style().size) for rect, block in cleared]
    ):
        return
    for rect, block in cleared:
        page.draw_rect(rect, color=None, fill=_fill_color(block), overlay=True)


#: Of the page's area, how much one image must cover to be taken as the scan itself.
_SCAN_IMAGE_COVERAGE = 0.9

#: Median saturation (0-255) above which a box is not paper but a coloured panel. Ink erasing is
#: written for paper, and on a panel the Otsu split puts the BACKGROUND in the ink population: it
#: then erases the panel and leaves the original text showing, while returning True so the caller's
#: rectangle fill never ran. Measured medians: 201, 201, 202 on the Elmasri cover's title, boxes and
#: 52-56 on the yellowed paper of the 1895 mushroom scans - 120 sits between them with room.
_SCAN_PAPER_MAX_SATURATION = 120


def _scan_pixels(pixmap: pymupdf.Pixmap) -> np.ndarray:
    """The scan's pixels as an H x W x 3 uint8 array.

    WHY THIS EXISTS: the whitening pass once rebuilt the buffer with a hard-coded three channels,
    and a page whose scan image carries alpha died on `cannot reshape array of size 32770400 into
    shape (3425, 2392, 3)` - the scanned Eleventh Development Plan, whose page image measures
    `n=4, alpha=1`. PyMuPDF *keeps* an alpha channel across a `csRGB` conversion, so converting
    first and reshaping afterwards is not enough. The chunk wrote nothing, the document was a chunk
    short and the merge refused to build a document with a hole. Alpha is dropped first
    (`Pixmap(pix, 0)` measured to give `n=3, alpha=0`), the reshape uses the pixmap's own component
    count, and the last guard covers a source that still refuses to give its alpha up.
    """
    if pixmap.alpha:
        pixmap = pymupdf.Pixmap(pixmap, 0)
    if pixmap.n != 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    import numpy as np  # local, like the rest of this module: numpy is not needed to write a PDF

    pixels = np.frombuffer(pixmap.samples, np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n).copy()
    if pixels.shape[2] != 3:
        pixels = pixels[:, :, :3]
    return pixels


def _erase_ink_from_scan(page: pymupdf.Page, rects: list[tuple[pymupdf.Rect, float]]) -> bool:
    """Remove the ink inside `rects` from the page's scanned image itself. True if it did.

    A flat rectangle of the block's average background leaves a visible edge on any paper that
    is not one colour - a yellowed or unevenly lit scan, where the NASA report's cover runs from
    174 to 206 on a single page, and every translated block sat on a patch. Only the ink is taken
    out here, and the paper under it is continued from the paper around it, so the texture and
    shading of the scan survive.

    Ink is what is darker than its own box's paper, by Otsu's threshold over that box: a text box
    is two populations by construction, so the split is measured per box rather than set. A rule
    crossing the box is dark too, and clearing a table's header erased the table's lines (book
    page 101); so a straight run longer than twice the box's type size, across or down, is kept -
    no glyph stroke is that long.

    The cleaned area is placed over the scan as a lossless patch on the scan's own pixel grid;
    the scan image itself is never re-encoded, so every pixel outside the cleared boxes stays
    bit-identical - re-encoding the whole page as JPEG changed a figure no block touched.

    Declines - and the caller paints rectangles as before - when OpenCV is not installed, or the
    page has no single axis-aligned image covering it.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False

    page_area = page.rect.width * page.rect.height
    scan = None
    for info in page.get_image_info(xrefs=True):
        a, b, c, d, _e, _f = info["transform"]
        x0, y0, x1, y1 = info["bbox"]
        if (
            info.get("xref")
            and abs(b) < 1e-6 and abs(c) < 1e-6 and a > 0 and d > 0
            and (x1 - x0) * (y1 - y0) >= page_area * _SCAN_IMAGE_COVERAGE
        ):
            scan = info
            break
    if scan is None:
        return False

    #: Set when a box was actually cleaned from the scan's own pixels.
    cleaned_any = False
    #: Set when a box turned out not to be paper at all - a coloured cover, where erasing "ink"
    #: would erase the panel and leave the original text showing. The caller must then paint.
    declined = False

    document = page.parent
    pixmap = pymupdf.Pixmap(document, scan["xref"])
    pixels = _scan_pixels(pixmap)

    x0, y0, x1, y1 = scan["bbox"]
    sx, sy = pixmap.width / (x1 - x0), pixmap.height / (y1 - y0)
    # Anti-aliased glyph edges are lighter than the Otsu split; reach half a point past it.
    reach = max(1, round(0.5 * min(sx, sy)))
    kernel = np.ones((3, 3), np.uint8)
    for rect, type_size in rects:
        px0 = max(0, int((rect.x0 - x0) * sx))
        py0 = max(0, int((rect.y0 - y0) * sy))
        px1 = min(pixmap.width, math.ceil((rect.x1 - x0) * sx))
        py1 = min(pixmap.height, math.ceil((rect.y1 - y0) * sy))
        if px1 - px0 < 2 or py1 - py0 < 2:
            continue
        # Work on the box plus a margin, so the fill has paper around it to continue from; the
        # mask itself never leaves the box.
        mx0, my0 = max(0, px0 - 2 * reach), max(0, py0 - 2 * reach)
        mx1, my1 = min(pixmap.width, px1 + 2 * reach), min(pixmap.height, py1 + 2 * reach)
        crop = pixels[my0:my1, mx0:mx1]
        grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        box = grey[py0 - my0 : py1 - my0, px0 - mx0 : px1 - mx0]
        # Paper is grey; a coloured panel is not. On the Eleventh book's cover the Otsu split put the
        # RED BACKGROUND in the "ink" population and the yellow title in the "paper" one, so this
        # function erased the background and left the original title showing - and returned True, so
        # the rectangle fill the caller keeps as a fallback never ran. Median saturation tells the two
        # apart without guessing at colours: measured 190+ on that cover, under 40 on paper scans.
        box_saturation = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)[
            py0 - my0 : py1 - my0, px0 - mx0 : px1 - mx0, 1
        ]
        if float(np.median(box_saturation)) > _SCAN_PAPER_MAX_SATURATION:
            declined = True
            continue
        _threshold, ink = cv2.threshold(box, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        run = max(3, round(2 * max(type_size, 1.0) * min(sx, sy)))
        rules = cv2.bitwise_or(
            cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, run), np.uint8)),
            cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((run, 1), np.uint8)),
        )
        keep = cv2.dilate(rules, kernel, iterations=reach + 1)
        erase = cv2.bitwise_and(cv2.dilate(ink, kernel, iterations=reach), cv2.bitwise_not(keep))
        mask = np.zeros(grey.shape, np.uint8)
        mask[py0 - my0 : py1 - my0, px0 - mx0 : px1 - mx0] = erase
        if not mask.any():
            continue
        cleaned = cv2.inpaint(crop, mask, 3, cv2.INPAINT_TELEA)
        pixels[my0:my1, mx0:mx1] = cleaned  # later boxes continue from already-cleaned paper
        ok, encoded = cv2.imencode(".png", cv2.cvtColor(cleaned, cv2.COLOR_RGB2BGR))
        if not ok:
            page.draw_rect(rect, color=None, fill=(1.0, 1.0, 1.0), overlay=True)
            continue
        page.insert_image(
            pymupdf.Rect(x0 + mx0 / sx, y0 + my0 / sy, x0 + mx1 / sx, y0 + my1 / sy),
            stream=encoded.tobytes(),
            overlay=True,
        )
        cleaned_any = True
    # Only a pass that cleaned EVERY box may claim success: otherwise the caller paints rectangles
    # for all of them, and a page half-cleaned and half-painted would show both treatments at once.
    return cleaned_any and not declined


def _fill_color(block: Block) -> tuple[float, float, float]:
    """The block's detected background as a pymupdf colour, defaulting to white."""
    background = block.dominant_style().background
    if not background:
        return (1.0, 1.0, 1.0)
    hex_digits = background.lstrip("#")
    if len(hex_digits) != 6:
        return (1.0, 1.0, 1.0)
    try:
        return tuple(int(hex_digits[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (1.0, 1.0, 1.0)
