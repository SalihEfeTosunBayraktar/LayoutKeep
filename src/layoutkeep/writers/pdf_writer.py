"""PDF writer: applies a translated DocIR Document back onto the original PDF file.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-pdf.md): the source PDF is opened once
more; for every block whose role is translatable (`Block.translatable`), the source glyphs
inside the block's bbox are removed with the redaction workflow and the block's current text -
the translation once the pipeline has applied it, or the original text if it has not been
translated yet - is drawn back into the same box with `insert_htmlbox`, styled span by span.
Blocks that are not translatable (page numbers, formulas, code, figures) are left untouched -
their pixels never move. Background images and vector art are explicitly protected from the
redaction step, whose defaults would otherwise delete them.
This is one of only two modules allowed to `import pymupdf` (see CONTRACT.md §4).

Font selection: a block is drawn with the font `fitting/fontmatch.resolve_font()` picked for
it, not a generic serif/sans/monospace guess - see `_FontResolver`. `Style.font_path` is read
first (the seam `core/docir.py` documents for "the fitting stage" to fill); if it is unset this
module resolves the font itself, since it is the one place with the source PDF still open and
therefore the only place that can check whether the *original* embedded font already covers the
target language's glyphs (`resolve_font`'s `embedded_font_bytes` argument) rather than assuming
a substitution is needed. Whatever gets resolved is subset to the characters this document
actually draws with `fontTools.subset` before embedding, so 17 bundled fonts don't turn into a
full face per document.
"""

from __future__ import annotations

import contextlib
import html as html_escapes
import io
import math
import re
import string
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pymupdf
from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont as FTFont
from fontTools.ttLib import TTLibError
from fontTools.varLib.instancer import instantiateVariableFont

from layoutkeep.core import tunables
from layoutkeep.core.docir import BBox, Block, Document, Span, Style
from layoutkeep.fitting import rotated_block_fits
from layoutkeep.fitting.fit import min_scale_setting
from layoutkeep.fitting.fontmatch import FontMatch, MatchQuality, resolve_font
from layoutkeep.fitting.growth import free_below, may_grow
from layoutkeep.fitting.room import room_below

if TYPE_CHECKING:  # numpy is imported where it is used: writing a PDF does not need it
    import numpy as np

#: `insert_htmlbox`'s own line-height/padding model is not pixel-identical to the tight glyph
#: bbox `pdf_reader.py` measures, so even untouched text can be a point or two taller than its
#: source bbox, and the writer must let `insert_htmlbox` absorb that gap. It may not go further
#: than that: this is the same readability floor `fitting/` shrinks to (D3 is still fitting's
#: job), so the writer can no longer quietly undercut a decision fitting already made and
#: flagged. See `_draw_block` for what happens when the floor is not enough.
_WRITE_SCALE_LOW_KEY = "fit.min_scale"  # the writer shares fitting's floor
#: Draw each inline run at its own size instead of the block's. Off by default: it is the subject of
#: an A/B (the per-box instrument counts 6-15 boxes per document where a smaller run is drawn at its
#: block's size) and it can move line heights, so nothing changes for a user until that is measured.
_INLINE_SPAN_SIZES_KEY = "writer.inline_span_sizes"
_BOX_SLACK_KEY = "write.box_slack_pt"

#: Below this many degrees a block is treated as ordinary horizontal text - noise in pymupdf's
#: `dir` vector, not an actual rotation. Matches `pdf_reader.py`'s own tolerance.
_ROTATION_EPS = 0.5
#: `insert_htmlbox`'s line-height guess, reused for stacking a rotated block's lines.
#:
#: Read from the tunable rather than declared here, because the reader derives a scanned block's
#: font size so that size x this ratio reproduces the line pitch it measured off the page. The
#: two must agree or every scanned page is mis-sized, and 1.2 used to be written out separately
#: in both files with nothing enforcing it.
_LINE_HEIGHT_KEY = "merge.line_height_ratio"


def writer_line_height_ratio() -> float:
    """How tall a line is stacked, as a multiple of the font size. Read at use, so a changed
    setting is seen without reimporting the module."""
    return tunables.get(_LINE_HEIGHT_KEY)


#: PDF base-14 font names, keyed by (generic family, bold, italic). Fallback for the rotated-text
#: path (needs a real `pymupdf.Font`, not a CSS family name) and for any block whose font could
#: not be resolved to a real file at all - see `_FontResolver`.
_BASE14 = {
    ("sans-serif", False, False): "helv",
    ("sans-serif", True, False): "hebo",
    ("sans-serif", False, True): "heit",
    ("sans-serif", True, True): "hebi",
    ("serif", False, False): "tiro",
    ("serif", True, False): "tibo",
    ("serif", False, True): "tiit",
    ("serif", True, True): "tibi",
    ("monospace", False, False): "cour",
    ("monospace", True, False): "cobo",
    ("monospace", False, True): "coit",
    ("monospace", True, True): "cobi",
}

#: Characters kept in every subset regardless of what the document actually uses, so
#: `insert_htmlbox`'s own layout (wrapping, hyphenation fallback, whitespace) never hits a
#: missing glyph even when the translated text happens not to contain some of them.
_ALWAYS_KEEP_CHARS = string.ascii_letters + string.digits + string.punctuation + " \n"

_SUBSET_TAG_RE = re.compile(r"^[A-Z]{6}\+")

#: What a malformed or unusual font file (bad table, unsupported flavour, truncated data) raises
#: across fontTools' loading, instancing and subsetting - caught wherever a font resolved from
#: an untrusted source PDF or a bundled file on disk must not take the whole write down with it.
_FONT_LOAD_ERRORS = (TTLibError, OSError, ValueError, KeyError, AssertionError)


def _clearing_reaches(kept: Block, changed: Block) -> bool:
    """Would clearing `changed` erase a glyph of `kept`?

    Redaction removes every glyph its box touches, so the question is asked of the kept block's
    own lines, not of the union box it was read with. A footer block holding a footnote and the
    URL beside it has a union box that covers the footnote's - but neither of its lines touches
    the footnote, and redrawing it moved the URL's first row 82pt left, over the footnote, which
    is how arXiv 2507.03009 came back with a word pair drawn over another (L7) that the source
    never had.

    A block with no measured lines falls back to its box: better to redraw one block needlessly
    than to let a redaction eat its text. The box is also grown by a point first - a redaction
    takes whole glyphs, and a glyph's own box can stick out of its line's by a fraction. Touching
    edges are not a reach: a footer's footnote sits one point above the URL's second row, and
    counting that as a hit redrew the URL and moved it over the footnote again.
    """
    area = _rect(changed.bbox)
    area = pymupdf.Rect(area.x0, area.y0, area.x1 + 1.0, area.y1 + 1.0)
    lines = [line for line in kept.lines if line.bbox is not None]
    if not lines:
        return not (_rect(kept.bbox) & area).is_empty
    return any(not (_rect(line.bbox) & area).is_empty for line in lines)


def write_pdf(doc: Document, src_path: str | Path, out_path: str | Path) -> None:
    """Render `doc` (read from `src_path`, possibly with translations applied) to `out_path`."""
    with pymupdf.open(str(src_path)) as pdf:
        resolver = _FontResolver(doc.target_lang)
        page_blocks: list[tuple[pymupdf.Page, list[Block], list[Block], bool, list[Block]]] = []
        for page_data in doc.pages:
            page = pdf[int(page_data.source_ref)]
            # A block whose translation is its source - a name, a document code, a running header
            # - is left exactly as set: removing and redrawing it only loses its typography
            # (small caps redrawn in a wider substitute were shrunk below the readability floor on
            # every NIST page).
            changed = [b for b in page_data.blocks if b.translatable and not _unchanged(b)]
            # ...unless the clearing of a changed neighbour would reach it: redaction removes every
            # glyph its box touches, and NIST's DOI line, 3pt inside the box of the sentence above
            # it, vanished from the page. Such a block is redrawn like any other.
            # Transitively: a kept block that is redrawn is cleared too, and its clearing can reach
            # the next kept block (NIST references: a URL's second line, two steps from the entry
            # that was translated, vanished).
            blocks = list(changed)
            waiting = [b for b in page_data.blocks if b.translatable and _unchanged(b)]
            grew = True
            while grew:
                grew = False
                for candidate in list(waiting):
                    if any(_clearing_reaches(candidate, c) for c in blocks):
                        blocks.append(candidate)
                        waiting.remove(candidate)
                        grew = True
            if not blocks:
                continue
            # Font resolution runs before any page is redacted: it may need to read the source
            # PDF's own embedded font bytes (`_extract_embedded_font_bytes`), and there is no
            # reason to depend on `apply_redactions` leaving font resources alone longer than
            # necessary.
            for block in blocks:
                resolver.register(page, block)
            kept = [b for b in page_data.blocks if not b.translatable]
            page_blocks.append(
                (page, blocks, kept, page_data.scanned, page_data.blocks, page_data.images)
            )
        resolver.finalize()

        for page, blocks, kept, scanned, everything, pictures in page_blocks:
            if scanned:
                # A searchable scan also carries an invisible OCR text layer over the image. Left
                # in place, the output looks translated and searches, copies and reads aloud in
                # the source language. Text only - the image is the page and is not redacted.
                redact_keeping_forms(page, [_rect(b.bbox) for b in blocks if not is_wordless(b)])
                _cover_scanned_blocks(page, blocks, keep=kept)
            else:
                areas: list[pymupdf.Rect | pymupdf.Quad] = []
                for block in blocks:
                    if abs(block.rotation) > _ROTATION_EPS:
                        # A rotated line's axis-aligned bbox is bigger than its glyphs (see
                        # `Block.rotation`'s docstring); redacting that whole rectangle would eat
                        # into whatever sits in its corners. Redact the actual glyph quads instead.
                        areas.extend(_rotated_quads(page, block))
                    else:
                        areas.append(_rect(block.bbox))
                redact_keeping_forms(page, areas)
            for block in blocks:
                if scanned and is_wordless(block):
                    # Left exactly as scanned - see `_MIN_WORDINESS`. Nothing was cleared under
                    # it either, so skipping the draw leaves the original pixels in place.
                    continue
                if abs(block.rotation) > _ROTATION_EPS:
                    _write_rotated_block(page, block, resolver)
                else:
                    html = f"<p>{_block_html(block, resolver)}</p>"
                    css = _css_for_block(block, resolver)
                    room = room_below(block, everything, float(tunables.get(_BOX_SLACK_KEY)))
                    # A block the pipeline actually translated may use the room the page has under
                    # it (`fitting/growth.py`) - the fitting pass measured against exactly this.
                    # A block kept as it was is drawn in its own box: its text is where the source
                    # put it, and more room could re-wrap a line and move it (L8). A running header,
                    # title or page number keeps its one-line box for the same reason.
                    grant = (
                        free_below(block, everything, obstacles=pictures)
                        if not _unchanged(block) and may_grow(block)
                        else 0.0
                    )
                    rect = _layout_rect(block.bbox, room, grant)
                    _draw_block(page, rect, html, css, resolver.archive)
        # `garbage=4` dedupes identical objects: every block drawn in a given resolved font
        # embeds its own copy of that font's subset bytes (`insert_htmlbox`'s own font-loading
        # does not share a face across separate calls, even given the same `archive`), and since
        # `_subset_font` produces byte-identical output for the same (font, characters) pair,
        # `garbage=4` collapses those duplicates back into one object at save time instead of
        # leaving 17 bundled fonts' worth of repeated subsets in the output.
        pdf.save(str(out_path), garbage=4, deflate=True)


#: How far outside its tight OCR box a block is painted over, in points. OCR reports the box of
#: the glyphs it recognised; ascenders, descenders and anti-aliased edges sit a fraction outside
#: it, and leaving that fringe behind puts a grey ghost of the source line under the
#: translation. Kept small - this paint is opaque, so every extra point is page content
#: destroyed for nothing.
_SCAN_COVER_PAD = 1.5


#: Letters per character, below which a block carries no words and is left as scanned.
#:
#: OCR reads a Karnaugh map or a truth table correctly character by character but has no idea
#: the digits form a grid, so it returns one block per horizontal run. Re-typesetting that run
#: as a line of prose destroys the figure: page 28 of `computer-systems-Architecture.pdf` came
#: back with `{123`, `{14576` and `1112131514 A 108` where its maps had been.
#:
#: OCR confidence cannot tell these apart - `1112131514 A 108` is reported at 1.00, because the
#: recognition is right and it is the two-dimensional structure that is lost. What does tell
#: them apart is words. Measured over that page's 34 blocks, the grid fragments run 0.00 to 0.18
#: letters per character and the real text ('(a) Two-variable map', 'adjacent squares') 0.50 to
#: 1.00, with nothing in between.
#:
#: Such a block has nothing to translate - protection already answers it with its own source -
#: so redrawing it cannot improve it, and measurably makes it worse.
_MIN_WORDINESS = 0.3

_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def is_wordless(block: Block) -> bool:
    """True when a block carries essentially no letters, only digits and punctuation.

    Judged on the source text where there is one (`Block.source_text`, set when a translation
    overwrites the block), because the question is whether this block ever had words to
    translate - not what came back. A grid of digits answered with a grid of digits would read
    the same either way, but a reply that arrived as prose would otherwise talk the writer into
    re-typesetting a figure it should have left alone.
    """
    text = (block.source_text or block.text).strip()
    if not text:
        return True
    return len(_LETTER_RE.findall(text)) / len(text) < _MIN_WORDINESS


def redact_keeping_forms(page: pymupdf.Page, areas: list) -> None:
    """Remove the text under `areas`, without disturbing forms the redaction did not touch.

    Applying redactions makes MuPDF rewrite the page, and it substitutes a rewritten copy for every
    form XObject on it - even one no area touches. In that copy text can move: Think Python's Figure
    3.1 had 8 of 11 labels up to 11 pt lower after redacting the running header 150 pt above it.
    So each rewritten form is restored from the original, and the restoration kept only if nothing
    the areas were meant to remove has come back with it.
    """
    document = page.parent
    before = [xobject[0] for xobject in page.get_xobjects()]
    for area in areas:
        page.add_redact_annot(area, cross_out=False, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    after = [xobject[0] for xobject in page.get_xobjects()]
    if not areas or len(before) != len(after):
        return
    rects = [area.rect if isinstance(area, pymupdf.Quad) else pymupdf.Rect(area) for area in areas]

    def removed_text_is_back() -> bool:
        for word in page.get_text("words"):
            middle = pymupdf.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)
            if any(rect.contains(middle) for rect in rects):
                return True
        return False

    for original, rewritten in zip(before, after, strict=True):
        if original == rewritten:
            continue
        saved_object = document.xref_object(rewritten)
        saved_stream = document.xref_stream(rewritten)
        try:
            # The whole object at once: `xref_copy` sets key by key, and a value holding a path -
            # pdfLaTeX's `/PTEX.FileName (./vocab_venn5.pdf)` on every included figure - was parsed
            # as a key path and raised, taking the whole page with it (held-out arXiv 2609.19145).
            document.update_object(rewritten, document.xref_object(original))
            document.update_stream(rewritten, document.xref_stream(original))
        except (pymupdf.mupdf.FzErrorBase, RuntimeError, ValueError):
            # A form that cannot be restored keeps MuPDF's rewrite: text inside it may sit a little
            # off, which verification reports (L8), rather than the page being lost.
            document.update_object(rewritten, saved_object)
            document.update_stream(rewritten, saved_stream)
            continue
        if removed_text_is_back():
            document.update_object(rewritten, saved_object)
            document.update_stream(rewritten, saved_stream)


def _unchanged(block: Block) -> bool:
    """The written text is the source exactly - letter case included, since a change of case is
    a change on the page. Markers and whitespace are not compared.

    A block with no `source_text` was never translated: the pipeline records the original only
    when a segment came back translated (`apply_segments`), so an empty one means the text on the
    block is still the source - the batch it was in failed, or it was never sent. Reading that as
    "changed" redrew those blocks in a substitute face for nothing, and a redrawn block is laid
    out from its own box's left edge: arXiv 2507.03009's footer URL came back 82pt left of where
    the source set it, over the footnote beside it (L7).
    """
    if not block.source_text:
        return True

    def plain(text: str) -> str:
        return " ".join(re.sub(r"</?\d+>", "", text).split())

    return plain(block.source_text) == plain(block.text)


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
    return True


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


def measure_fit(
    text: str, style: Style, bbox: BBox, *, scale_low: float = 0.85, rotation: float = 0.0
) -> tuple[bool, float]:
    """Check whether `text` rendered in `style` fits `bbox`. The seam `fitting/` calls through -
    it never imports pymupdf itself.

    Returns `(fits, scale)`. `fits` is False when even shrinking down to `scale_low` is not
    enough (mirrors `insert_htmlbox`'s `spare_height == -1`). Runs against a private scratch
    document, so it never touches the document being translated.

    `rotation` is `Block.rotation` in degrees (core/docir.py); `fit.fit_segment` always passes it
    as a keyword (see `fitting/measure.py`'s `MeasureFn` contract), so this must accept it even
    though ordinary horizontal text ignores it. Below `_ROTATION_EPS` this is the ordinary
    `insert_htmlbox` path unchanged. Above it, the block will be drawn by `_write_rotated_block`'s
    `TextWriter` instead, which does no wrapping and no shrink-to-fit of its own - so this checks
    the same thing that path actually draws against the honest rotated room from
    `fitting.rotated_block_fits`, rather than asking `insert_htmlbox` to lay text into the bigger,
    axis-aligned `bbox` it would otherwise use.

    If `style.font_path` is set (the fitting stage already resolved a real font - see
    `_FontResolver`), measurement uses that exact file. This matters: `write_pdf` draws with the
    resolved font's real metrics, and measuring against a different, generic-family guess would
    shrink or overflow text based on the wrong font's widths. Without it, this falls back to the
    same generic-family guess as before - resolving a font from scratch here would need a target
    language this function's signature has no room for (see the PDF writer agent's report on the
    `Style.font_path` seam).
    """
    if abs(rotation) <= _ROTATION_EPS:
        scratch = pymupdf.open()
        try:
            page = scratch.new_page(width=bbox.x1 + 50, height=bbox.y1 + 50)
            html = f"<p>{_escape_text(text)}</p>"
            family, archive = _measure_horizontal_source(style)
            css = (
                f"p {{ font-family: {family}; font-size: {style.size:.2f}pt; "
                f"color: {style.color}; font-weight: {'bold' if style.bold else 'normal'}; "
                f"font-style: {'italic' if style.italic else 'normal'}; margin: 0; }}"
            )
            if archive is not None:
                css = f'@font-face {{ font-family: "{family}"; src: url(measure.ttf); }} ' + css
            spare, scale = page.insert_htmlbox(
                _layout_rect(bbox), html, css=css, scale_low=scale_low, archive=archive
            )
            # A layout that fits only because it stopped early is not a fit (see `_laid_out_whole`).
            return spare != -1 and _laid_out_whole(page.get_text(), html), scale
        finally:
            scratch.close()

    lines = text.split("\n") or [""]
    font = _measure_rotated_font(style)
    steps = 16
    for i in range(steps + 1):
        scale = 1.0 - (1.0 - scale_low) * i / steps
        size = style.size * scale
        longest = max((font.text_length(ln, fontsize=size) for ln in lines), default=0.0)
        depth = len(lines) * size * writer_line_height_ratio()
        if rotated_block_fits(bbox, rotation, longest, depth):
            return True, scale
    return False, scale_low


def _measure_horizontal_source(style: Style) -> tuple[str, pymupdf.Archive | None]:
    """CSS family name plus a matching one-file `Archive` when `style.font_path` is set, else
    the old generic-family keyword with no archive at all."""
    if style.font_path:
        return "MeasureFont", pymupdf.Archive(style.font_path, "measure.ttf")
    return _generic_family(style.font_family, style.serif), None


def _measure_rotated_font(style: Style) -> pymupdf.Font:
    if style.font_path:
        return pymupdf.Font(fontfile=style.font_path)
    return pymupdf.Font(fontname=_base14_font(style))


def _draw_block(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    html: str,
    css: str,
    archive: pymupdf.Archive | None,
) -> None:
    """Draw one block, keeping it readable where that is possible and present where it is not.

    `insert_htmlbox` shrinks the text until it fits, and given a free hand it will shrink past
    the point of legibility - a 7pt footer came back at 3.9pt on a real document, after
    `fitting/` had already decided 0.85 was as far as it would go and flagged the block for
    review. Passing the same floor stops the writer undercutting that decision.

    `rect` comes from `_layout_rect`, which is also what the measurement was taken against.

    When the floor is not enough, `insert_htmlbox` draws *nothing at all* and reports -1 (not
    clipped text - none), so the call is repeated with the floor lifted: the text ends up smaller
    than it should be, but it is on the page, and the block carries fitting's review flag saying
    so. Losing it silently would be the worse failure.
    """
    # Laid out on a scratch page first: `insert_htmlbox` can report a fit and draw only the first
    # lines (see `_laid_out_whole`), and on the real page there is no taking a draw back.
    attempts = [(rect, min_scale_setting()), (rect, 0)]
    attempts += [(pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y1 + extra), 0) for extra in (0.5, 1.0, 2.0)]
    for box, scale_low in attempts:
        if _lays_out_whole(box, html, css, scale_low, archive):
            page.insert_htmlbox(box, html, css=css, scale_low=scale_low, archive=archive)
            return
    # Nothing tried holds the whole text; draw it shrunk anyway rather than not at all, and let
    # verification report what is missing (L3).
    page.insert_htmlbox(attempts[-1][0], html, css=css, scale_low=0, archive=archive)


def _lays_out_whole(
    rect: pymupdf.Rect, html: str, css: str, scale_low: float, archive: pymupdf.Archive | None
) -> bool:
    scratch = pymupdf.open()
    try:
        page = scratch.new_page(width=rect.x1 + 50, height=rect.y1 + 50)
        spare, _scale = page.insert_htmlbox(rect, html, css=css, scale_low=scale_low, archive=archive)
        return spare >= 0 and _laid_out_whole(page.get_text(), html)
    finally:
        scratch.close()


def _laid_out_whole(drawn: str, html: str) -> bool:
    """Whether a layout holds all of the text it was given.

    `insert_htmlbox` has a boundary case: when the box is exactly as tall as the lines it holds - a
    10 pt glyph box plus the 3 pt slack is 13 pt, one line of 10 pt text - it reports a fit (spare
    0, scale 1.0) and lays out only the first line. Held-out PLOS ONE: eight one-line blocks lost
    their last words that way, with neither fitting nor the writer noticing. Compared without
    whitespace and hyphens, which the layout adds, and with ligatures unfolded.
    """
    def comparable(text: str) -> str:
        return unicodedata.normalize("NFKC", re.sub(r"[\s­-]+", "", text))

    expected = html_escapes.unescape(re.sub(r"<[^>]+>", "", html))
    return comparable(expected) in comparable(drawn)


def _layout_rect(
    bbox: BBox, room_below: float | None = None, grant_below: float = 0.0
) -> pymupdf.Rect:
    """The box `insert_htmlbox` is given for a block, which is not quite the box the reader
    measured.

    The reader records the tight glyph box. `insert_htmlbox` needs more than that - it keeps its
    own inset, and lays out against the room that is left. On a paragraph the difference is
    nothing; on a short label it is most of the width, and the text gets shrunk to fit a box its
    own glyphs already fill. Measured on a chart axis: "0.6" at 6pt, in the 8.3pt-wide box its
    glyphs occupy, came out at 4.4pt - a number the translation never touched, shrunk by the
    renderer's padding alone.

    The allowance is added to the right and below only, never the left or top, so the first
    glyph still starts where the source's did. `measure_fit` and the draw both go through here:
    when they disagreed, fitting decided a label had to shrink and the writer then shrank it
    again from there.
    """
    slack = float(tunables.get(_BOX_SLACK_KEY))
    rect = _rect(bbox)
    # Below, only as much as the page has free (`fitting.room`): paragraphs set close together have
    # none, and the slack drew the last line of one over the first line of the next. `grant_below`
    # is the room the page really has under the block (`fitting.growth`), which the fitting pass
    # measured against - the same number, or the two disagree and the text is shrunk twice.
    below = slack if room_below is None else min(slack, room_below)
    # Never shorter than a sliver: a box the next block starts right below the top of is still
    # given a line's worth of height, and its text shrinks rather than vanishing.
    bottom = max(
        rect.y1 + below + max(0.0, grant_below),
        rect.y0 + min(rect.height, _MIN_DRAW_HEIGHT),
    )
    return pymupdf.Rect(rect.x0, rect.y0, rect.x1 + slack, bottom)


#: The least height a block is drawn in, whatever overlaps it from below.
_MIN_DRAW_HEIGHT = 6.0


def _rect(bbox: BBox) -> pymupdf.Rect:
    return pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)


def _rotated_quads(page: pymupdf.Page, block: Block) -> list[pymupdf.Quad]:
    """The exact glyph quads under a rotated block, read straight from the still-untouched page.

    `block.bbox` is the axis-aligned box `pdf_reader.py` measured, which is larger than the
    rotated glyphs it contains, so it cannot be used for redaction directly. This re-extracts the
    page's own line boxes inside that bbox and asks pymupdf's `search_for(..., quads=True)` for
    each line's real quadrilateral. If a line's text cannot be re-found (rare: ligature
    normalisation, spacing), its axis-aligned line bbox is used as a fallback quad - narrower
    than the whole block, so still an improvement over redacting the block's full bbox.
    """
    quads: list[pymupdf.Quad] = []
    clip = _rect(block.bbox)
    for raw in page.get_text("dict", clip=clip).get("blocks", []):
        if raw.get("type") != 0:
            continue
        for raw_line in raw.get("lines", []):
            dx, dy = raw_line.get("dir", (1.0, 0.0))
            angle = math.degrees(math.atan2(dy, dx))
            if abs(angle - block.rotation) > _ROTATION_EPS:
                continue
            text = "".join(s.get("text", "") for s in raw_line.get("spans", []))
            if not text.strip():
                continue
            # Rect arithmetic, not concatenation: this grows the line box by a point on
            # every side so `search_for` has room to match the text it clips.
            line_rect = pymupdf.Rect(*raw_line["bbox"]) + (-1, -1, 1, 1)  # noqa: RUF005 - Rect arithmetic, not a list
            quads.extend(_line_quads(page, text, line_rect))
    return quads or [clip.quad]


#: How much of a line's own box the quads found under it must cover before they are trusted to
#: be the whole line. A rotated line's quads together fill its axis-aligned box; a hit that came
#: back as a fragment does not come close.
_COVERAGE_KEY = "redact.coverage_ratio"  # tunables key; read where it is used

#: Characters `search_for` can never match, because they carry no Unicode meaning: a symbol-
#: encoded font's private-use glyphs (an apostrophe or a bullet, commonly) and the replacement
#: character a broken encoding leaves behind.
_UNSEARCHABLE = re.compile("[\ue000-\uf8ff\ufffd\x00-\x1f]+")


def _line_quads(page: pymupdf.Page, text: str, line_rect: pymupdf.Rect) -> list[pymupdf.Quad]:
    """Every quad the glyphs of one line occupy - not just the first.

    `search_for` reports a hit as one quad per run of text it could follow, so a line broken by
    a character it cannot match comes back in pieces. Taking only the first piece redacted the
    beginning of the line and left the rest of the source on the page, where the translation was
    then drawn on top of it: two strings overlapping, both legible. Seen on a real document, on
    a rotated line whose apostrophe was a private-use glyph.

    When the quads that were found do not add up to the line's own box, the line is searched
    again in the runs between the unmatchable characters. If that still does not cover it, the
    line's box is redacted whole - it is one line wide, and leaving source text visible under a
    translation is the worse of the two failures.
    """
    found = page.search_for(text, clip=line_rect, quads=True)
    if _covers(found, line_rect):
        return found

    runs: list[pymupdf.Quad] = []
    for part in _UNSEARCHABLE.split(text):
        if part.strip():
            runs.extend(page.search_for(part, clip=line_rect, quads=True))
    if _covers(runs, line_rect):
        return runs
    return found or runs or [line_rect.quad]


def _covers(quads: list[pymupdf.Quad], line_rect: pymupdf.Rect) -> bool:
    """Whether these quads, taken together, account for the line's box."""
    if not quads:
        return False
    union = quads[0].rect
    for quad in quads[1:]:
        union |= quad.rect
    area = abs(line_rect.get_area())
    return bool(area) and abs(union.get_area()) / area >= tunables.get(_COVERAGE_KEY)


def _base14_font(style: Style) -> str:
    return _BASE14[(_generic_family(style.font_family, style.serif), style.bold, style.italic)]


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    h = color.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def _write_rotated_block(page: pymupdf.Page, block: Block, resolver: _FontResolver) -> None:
    """Draw a rotated block's text at its angle.

    `insert_htmlbox`'s `rotate` parameter only takes 0/90/180/270, so an arbitrary angle goes
    through `TextWriter` + a `morph` transform instead. The cost of leaving `insert_htmlbox`:
    this path has no shrink-to-fit of its own. It draws at `block.dominant_style().size` exactly
    as `fitting/` left it; if that size does not fit, this writer will not discover or correct
    it the way `insert_htmlbox`'s `scale_low` does for horizontal text.

    Placement is anchored on `block.bbox`'s centre rather than a per-glyph baseline: DocIR only
    keeps one rotation and one bbox per block, not the original per-line baselines, so the centre
    is the one point that stays meaningful after translation has rewritten the block down to a
    single `Line`.
    """
    dominant = block.dominant_style()
    font_bytes = resolver.font_bytes_for(dominant)
    font = pymupdf.Font(fontbuffer=font_bytes) if font_bytes else pymupdf.Font(fontname=_base14_font(dominant))
    lines = block.text.split("\n") or [""]
    line_height = dominant.size * writer_line_height_ratio()
    cx = (block.bbox.x0 + block.bbox.x1) / 2
    cy = (block.bbox.y0 + block.bbox.y1) / 2
    start_y = cy - (line_height * len(lines)) / 2 + dominant.size
    tw = pymupdf.TextWriter(page.rect, color=_hex_to_rgb(dominant.color))
    for i, text in enumerate(lines):
        width = font.text_length(text, fontsize=dominant.size)
        tw.append((cx - width / 2, start_y + i * line_height), text, font=font, fontsize=dominant.size)
    # `Block.rotation` is measured as atan2(dy, dx) straight off pymupdf's own `dir` vector;
    # `prerotate` turns out to need the negated angle to reproduce that same reading (verified
    # against a known test rotation - see the fixture round-trip test).
    matrix = pymupdf.Matrix(1, 1).prerotate(-block.rotation)
    tw.write_text(page, morph=(pymupdf.Point(cx, cy), matrix))


def _escape_text(text: str) -> str:
    # A control character is extraction noise - a symbol-font glyph with no mapping comes out as NUL
    # - and the HTML layout stops at a NUL, dropping the rest of the block while reporting a fit
    # (held-out PLOS ONE, page 13). It has no drawable form to keep.
    text = _CONTROL_CHARACTERS.sub("", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _generic_family(font_name: str, serif: bool | None = None) -> str:
    """Map a source PDF font name to one of the generic families pymupdf's HTML engine always
    knows, without needing a resolved font file. Fallback for blocks `_FontResolver` could not
    resolve to a real font file at all.

    The name decides when it can, as in `fontmatch.resolve_font`; when it cannot, the source's own
    serif flag does. By name alone URW Palladio, Nimbus Roman and Computer Modern all came out as
    sans - every paragraph of Think Python and of a pdfLaTeX paper redrawn in Helvetica."""
    from layoutkeep.fitting.fontmatch import FontClass, classify

    kind = classify(font_name)
    if kind is FontClass.MONO:
        return "monospace"
    if kind is FontClass.SERIF or (kind is FontClass.UNKNOWN and serif):
        return "serif"
    return "sans-serif"


def _span_html(span: Span, dominant: Style, resolver: _FontResolver) -> str:
    text = _escape_text(span.text)
    if not text:
        return ""
    style = span.style
    family = resolver.css_family_for(style)
    dominant_family = resolver.css_family_for(dominant)
    # `<i>`/`<b>` are always applied from the span's own flags, same as before this module
    # resolved real fonts at all: MuPDF synthesizes slant/weight on a face that does not have a
    # dedicated italic/bold instance, which today's font matcher does not always pick even when
    # one is bundled (a separate, already-known `fontmatch.find_family` limitation - see the PDF
    # writer agent's report). Layering the resolved family underneath, when it differs from the
    # dominant style's, still gets a genuinely different (if not always perfectly matched) face
    # in wherever the matcher did resolve one.
    if style.italic:
        text = f"<i>{text}</i>"
    if style.bold:
        text = f"<b>{text}</b>"
    if family != dominant_family:
        text = f'<span style="font-family:{family}">{text}</span>'
    if style.color != dominant.color:
        text = f'<span style="color:{style.color}">{text}</span>'
    # The block's CSS carries one `font-size`, so a run set smaller than its block - a superscript
    # marker, a footnote reference, a formula fragment - is drawn at the block's size. The per-box
    # instrument (`tools/audit/type_map.py`) counts 6-15 boxes per document where that happens.
    # Behind a setting: it changes line heights, and the A/B has to read L7 as well as `flattened`.
    if (
        tunables.get(_INLINE_SPAN_SIZES_KEY)
        and style.size
        and dominant.size
        and abs(style.size - dominant.size) > 0.05
    ):
        text = f'<span style="font-size:{style.size:.2f}pt">{text}</span>'
    return text


def _block_html(block: Block, resolver: _FontResolver) -> str:
    dominant = block.dominant_style()
    parts: list[str] = []
    for i, line in enumerate(block.lines):
        if i:
            parts.append("<br>")
        parts.extend(_span_html(span, dominant, resolver) for span in line.spans)
    return "".join(parts)


def _css_for_block(block: Block, resolver: _FontResolver) -> str:
    dominant = block.dominant_style()
    family = resolver.css_family_for(dominant)
    # A style that names its own line height is honoured here because the *measurement* already
    # honours it (`fitting/measure.py` reads `style.line_height`): without this rule the fit was
    # decided against one leading and the page drawn with another. The readers leave the field
    # unset today, so this is the seam the fitting ladder's "tighten the leading" step will use.
    leading = (
        f" line-height: {dominant.line_height:.2f}pt;"
        if dominant.line_height is not None
        else ""
    )
    return (
        f"{resolver.css_face_rules()} "
        f"p {{ font-family: {family}; font-size: {dominant.size:.2f}pt; color: {dominant.color}; "
        f"direction: {block.direction.value}; margin: 0; text-align: {_css_align(block)};"
        f"{leading} }}"
    )


def _css_align(block: Block) -> str:
    """The block's alignment as CSS. The box is as wide as its longest line, so without this
    every shorter line of a centred title started at the box's left edge (NASA report cover)."""
    return block.align if block.align in ("left", "center", "right", "justify") else "left"


# --------------------------------------------------------------------------------------
# Font resolution and embedding
#
# See the module docstring for the two design decisions this section makes: `Style.font_path`
# is read first and this module only resolves a font itself as a fallback, and the *original*
# embedded font is reused (via `resolve_font`'s `embedded_font_bytes` coverage check) rather than
# always substituting, because only this module still has the source PDF's font resources open.
# --------------------------------------------------------------------------------------


def _style_key(style: Style) -> tuple[str, bool, bool]:
    """Identity used to resolve a font once per (family, bold, italic) combination rather than
    once per block - real documents reuse the same handful of styles across many paragraphs."""
    return (style.font_family, style.bold, style.italic)


def _normalize_font_name(name: str) -> str:
    """Strip a PDF subset tag ('ABCDEF+') and casing so a page's font resource name (still
    tagged) and `Style.font_family` (pymupdf's `get_text('dict')` already strips the tag from
    this - see `readers/pdf_reader.py`) compare equal. Mirrors `fitting/fontmatch.py`'s own
    private `_normalize`, duplicated rather than imported since that name is not part of its
    public API."""
    return re.sub(r"[^a-z0-9]", "", _SUBSET_TAG_RE.sub("", name).lower())


def _extract_embedded_font_bytes(page: pymupdf.Page, font_family: str) -> bytes | None:
    """The exact bytes of the source PDF's own embedded font for `font_family`, if it can still
    be found in this page's Resources. Feeds `resolve_font`'s `embedded_font_bytes` coverage
    check so a font that already has the target language's glyphs is reused instead of
    substituted (see the module docstring). Returns None on anything unusual - an unmatched
    name, a font pymupdf cannot extract (e.g. Type1) - so the caller falls back to substitution,
    which is always the safe default per `resolve_font`'s own contract.
    """
    target = _normalize_font_name(font_family)
    if not target:
        return None
    try:
        for xref, _ext, _kind, basefont, *_rest in page.get_fonts(full=True):
            if _normalize_font_name(basefont) != target:
                continue
            extracted = page.parent.extract_font(xref)
            if len(extracted) >= 4 and extracted[3]:
                return extracted[3]
    except (RuntimeError, ValueError):
        return None
    return None


#: `usWeightClass` fontTools' instancer pins a variable font's `wght` axis to when `Style.bold`
#: is requested - the standard OpenType "Bold" weight. Several bundled substitutes (Arimo,
#: Noto Sans, Noto Serif - see `assets/fonts/`) ship as variable fonts with only a Regular named
#: instance, so without this a bold request would silently embed Regular weight glyphs.
_BOLD_WEIGHT = 700.0


def _pin_variable_weight(ttfont: FTFont, bold: bool) -> None:
    """Pin every axis of a variable font to a concrete instance - `wght` to Bold or the font's
    own default depending on `bold`, everything else (width, optical size, ...) to its default -
    so the embedded font is an ordinary static face with the requested weight actually baked
    into its outlines and `head.macStyle`/`OS/2.usWeightClass`, not a left-as-variable Regular.
    A no-op on a font that has no `fvar` table at all (already static, e.g. the bundled Bold/
    Italic files that exist as separate static faces - see `assets/fonts/README.md`).
    """
    fvar = ttfont.get("fvar")
    if fvar is None:
        return
    has_wght = any(axis.axisTag == "wght" for axis in fvar.axes)
    if not has_wght:
        return
    axes = {
        axis.axisTag: min(axis.maxValue, _BOLD_WEIGHT) if axis.axisTag == "wght" and bold else axis.defaultValue
        for axis in fvar.axes
    }
    # Best-effort weight fix: subsetting proceeds on whatever instance is default if it fails.
    with contextlib.suppress(_FONT_LOAD_ERRORS):
        instantiateVariableFont(ttfont, axes, inplace=True, updateFontNames=True)


def _subset_font(source: bytes | tuple[str, int], chars: str, *, bold: bool = False) -> bytes:
    """Subset `source` (raw font bytes, or `(path, font_number)` for a file on disk) down to the
    characters this document actually draws in that font, so bundling 17 full faces doesn't turn
    into embedding 17 full faces per document (see the module docstring)."""
    if isinstance(source, tuple):
        path, font_number = source
        ttfont = FTFont(path, fontNumber=font_number, lazy=False)
    else:
        ttfont = FTFont(io.BytesIO(source), lazy=False)
    options = ft_subset.Options()
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = False
    # Latin ligatures are dropped, and it is the text layer that needs them gone rather than the
    # page. Subsetting renumbers glyphs, and the ligature's entry in the map back to Unicode does
    # not survive it: "İstifleme" drew correctly and copied out of the finished PDF as
    # "İsti{eme". Even unsubsetted it copies as U+FB02, which no search for "fl" will match.
    # A document that cannot be searched or quoted is a poor result for a translator, and two
    # separate letters at 7pt look the same as the ligature did. Only the Latin features go;
    # `rlig` and the Arabic joining features stay, since those are not decoration.
    options.layout_features = [
        feature
        for feature in options.layout_features
        if feature not in ("liga", "clig", "dlig", "hlig")
    ]
    subsetter = ft_subset.Subsetter(options=options)
    subsetter.populate(text=chars + _ALWAYS_KEEP_CHARS)
    subsetter.subset(ttfont)
    # Pinned after subsetting, not before. Instancing a variable font merges its variation
    # tables across every glyph it has; doing that to the whole face and then throwing away
    # all but the hundred glyphs the document uses costs 2.5x the time for a byte-identical
    # result (9 KB, 95 glyphs, same style flags either way).
    _pin_variable_weight(ttfont, bold)
    buf = io.BytesIO()
    ttfont.save(buf)
    return buf.getvalue()


def _matches_requested_style(font_bytes: bytes, *, bold: bool, italic: bool) -> bool:
    """Whether the font actually embedded (after subsetting/weight-pinning) carries the
    bold/italic flags it was resolved for, read from `head.macStyle` - the same bit pymupdf
    itself reports back as `flags` on redrawn text (see `_embed`'s caller)."""
    try:
        macstyle = FTFont(io.BytesIO(font_bytes), lazy=True)["head"].macStyle
    except _FONT_LOAD_ERRORS:
        return not bold and not italic
    return bool(macstyle & 0x1) == bold and bool(macstyle & 0x2) == italic


@dataclass(slots=True)
class _EmbeddedFont:
    css_family: str
    font_bytes: bytes


class _FontResolver:
    """Resolves each translatable block's dominant style to a real, glyph-complete font and
    subsets it down to the characters this document actually draws.

    Two passes, driven by `write_pdf`: `register()` walks every block *before* any page is
    redacted, so the source PDF's own embedded fonts are still there to check for glyph coverage;
    `finalize()` then subsets each resolved font once (not once per block) and builds the single
    `pymupdf.Archive` every page's `insert_htmlbox` call references.
    """

    def __init__(self, target_lang: str | None):
        self._target_lang = target_lang or ""
        self._chars: dict[tuple[str, bool, bool], set[str]] = {}
        self._preset_paths: dict[tuple[str, bool, bool], str] = {}
        self._matches: dict[tuple[str, bool, bool], FontMatch] = {}
        self._original_bytes: dict[tuple[str, bool, bool], bytes] = {}
        self._resolved: dict[tuple[str, bool, bool], _EmbeddedFont | None] = {}
        self._face_rules: list[str] = []
        self.archive = pymupdf.Archive()
        self._next_id = 0

    def register(self, page: pymupdf.Page, block: Block) -> None:
        # Every span's own style is resolved, not just the block's dominant one: a paragraph
        # commonly mixes a regular run with inline bold/italic runs (see `_span_html`), and each
        # needs its own real font file so `<b>`/`<i>` don't have to fall back to synthetic
        # weight/slant on a single embedded face.
        for line in block.lines:
            for span in line.spans:
                self._register_style(page, span.style, span.text)
        # `_write_rotated_block` redraws the whole block as one run in its dominant style, so
        # that key must be resolved too even for a block whose spans were otherwise covered.
        self._register_style(page, block.dominant_style(), block.text)

    def _register_style(self, page: pymupdf.Page, style: Style, text: str) -> None:
        key = _style_key(style)
        self._chars.setdefault(key, set()).update(text)
        if key in self._matches or key in self._preset_paths:
            return
        if style.font_path:
            # The fitting stage already resolved this style (see the module docstring) - trust
            # it rather than resolving again.
            self._preset_paths[key] = style.font_path
            return
        embedded = _extract_embedded_font_bytes(page, style.font_family)
        try:
            match = resolve_font(
                style.font_family or "sans-serif",
                self._target_lang,
                bold=style.bold,
                italic=style.italic,
                embedded_font_bytes=embedded,
                serif_hint=style.serif,
            )
        except _FONT_LOAD_ERRORS:
            # A font resolution failure must not take the whole write down - this style falls
            # back to the generic-family mapping (see `css_family_for`/`font_bytes_for`).
            return
        self._matches[key] = match
        if match.quality is MatchQuality.ORIGINAL and embedded is not None:
            self._original_bytes[key] = embedded

    def finalize(self) -> None:
        for key, path in self._preset_paths.items():
            self._embed(key, (path, 0))
        for key, match in self._matches.items():
            if match.quality is MatchQuality.ORIGINAL:
                raw = self._original_bytes.get(key)
                if raw is not None:
                    self._embed(key, raw)
                # else: covers_target was true but the bytes could not be re-extracted - leave
                # unresolved, the block falls back to the generic mapping.
            elif match.resolved_path:
                self._embed(key, (match.resolved_path, match.resolved_font_number))

    def _embed(self, key: tuple[str, bool, bool], source: bytes | tuple[str, int]) -> None:
        chars = "".join(sorted(self._chars.get(key, set())))
        _family, bold, italic = key
        try:
            subset_bytes = _subset_font(source, chars, bold=bold)
        except _FONT_LOAD_ERRORS:
            return
        if not _matches_requested_style(subset_bytes, bold=bold, italic=italic):
            # The resolved font does not actually deliver the requested weight/slant, so fall
            # back to the generic-family mapping, which at least gets a real bold/italic base-14
            # face via `<b>`/`<i>` rather than drawing upright or regular-weight text.
            #
            # This is now a genuine last resort rather than a routine path. It used to fire for
            # every bold-italic run in a Cousine, Caladea or Carlito document, because no
            # bold-italic file was bundled for those families and `find_family` returned their
            # upright italic - losing, silently, the metric compatibility the bundle exists for.
            # Those three faces are now shipped; `test_every_bundled_family_can_deliver_every_style`
            # keeps it that way.
            return
        css_family = f"LKFont{self._next_id}"
        self._next_id += 1
        entry_name = f"{css_family}.ttf"
        self.archive.add((subset_bytes, entry_name))
        self._face_rules.append(f'@font-face {{ font-family: "{css_family}"; src: url({entry_name}); }}')
        self._resolved[key] = _EmbeddedFont(css_family=css_family, font_bytes=subset_bytes)

    def css_face_rules(self) -> str:
        return " ".join(self._face_rules)

    def css_family_for(self, style: Style) -> str:
        resolved = self._resolved.get(_style_key(style))
        return resolved.css_family if resolved else _generic_family(style.font_family, style.serif)

    def font_bytes_for(self, style: Style) -> bytes | None:
        resolved = self._resolved.get(_style_key(style))
        return resolved.font_bytes if resolved else None
