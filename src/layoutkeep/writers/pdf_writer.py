"""PDF writer: applies a translated DocIR Document back onto the original PDF file.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-pdf.md): the source PDF is opened once
more; for every block whose role is translatable (`Block.translatable`), the source glyphs
inside the block's bbox are removed with the redaction workflow and the block's current text -
the translation once the pipeline has applied it, or the original text if it has not been
translated yet - is drawn back into the same box with `insert_htmlbox`, styled span by span.
Blocks that are not translatable (page numbers, formulas, code, figures) are left untouched -
their pixels never move. Background images and vector art are explicitly protected from the
redaction step, whose defaults would otherwise delete them.
pymupdf stays inside `readers/` and `writers/`: this module and its `_pdf_*` helpers may import it,
the core modules never do (see CONTRACT.md §4).

Bu modül giriş noktasıdır (`write_pdf`); ölçüm, çizim, işaretleme, yazı tipleri, redaksiyon,
tarama örtüsü ve kaynak bilgisi `writers/_pdf_*.py` modüllerindedir. This module is the entry
point; measuring, drawing, markup, fonts, redaction, scan covering and provenance live in
`writers/_pdf_*.py`.

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

from pathlib import Path

import pymupdf

from layoutkeep.core import provenance, tunables
from layoutkeep.core.docir import Block, Document
from layoutkeep.fitting.growth import free_below, free_right, may_grow, may_grow_right
from layoutkeep.fitting.room import room_below
from layoutkeep.writers._pdf_draw import _draw_block, _rotated_quads, _write_rotated_block
from layoutkeep.writers._pdf_fonts import _FontResolver
from layoutkeep.writers._pdf_markup import _block_html, _css_for_block, span_markup
from layoutkeep.writers._pdf_measure import _layout_rect, measure_fit
from layoutkeep.writers._pdf_provenance import _write_provenance, copy_provenance
from layoutkeep.writers._pdf_redaction import (
    _unchanged,
    is_wordless,
    link_underlines,
    redact_keeping_forms,
    same_text,
)
from layoutkeep.writers._pdf_scan_cover import _cover_scanned_blocks
from layoutkeep.writers._pdf_writer_common import (
    _BOX_SLACK_KEY,
    _ROTATION_EPS,
    _rect,
    writer_line_height_ratio,
)

# Dışa açık API buradan okunur; `fitting.pdf_pass` `measure_fit`'i çağrı anında bu modülden alır,
# testler de onu burada değiştirir. The public API is read from here: `fitting.pdf_pass` takes
# `measure_fit` from this module at call time, and the tests patch it here.
__all__ = [
    "copy_provenance",
    "is_wordless",
    "link_underlines",
    "measure_fit",
    "redact_keeping_forms",
    "same_text",
    "span_markup",
    "write_pdf",
    "writer_line_height_ratio",
]


#: `insert_htmlbox`'s own line-height/padding model is not pixel-identical to the tight glyph
#: bbox `pdf_reader.py` measures, so even untouched text can be a point or two taller than its
#: source bbox, and the writer must let `insert_htmlbox` absorb that gap. It may not go further
#: than that: this is the same readability floor `fitting/` shrinks to (D3 is still fitting's
#: job), so the writer can no longer quietly undercut a decision fitting already made and
#: flagged. See `_draw_block` for what happens when the floor is not enough.
_WRITE_SCALE_LOW_KEY = "fit.min_scale"  # the writer shares fitting's floor


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
                    if block.raster:
                        continue  # no text layer: its words are pixels, erased below
                    if abs(block.rotation) > _ROTATION_EPS:
                        # A rotated line's axis-aligned bbox is bigger than its glyphs (see
                        # `Block.rotation`'s docstring); redacting that whole rectangle would eat
                        # into whatever sits in its corners. Redact the actual glyph quads instead.
                        areas.extend(_rotated_quads(page, block))
                    else:
                        areas.append(_rect(block.bbox))
                # Found before the text goes: clearing a block also removes the links inside it.
                underlines = link_underlines(page, [b for b in blocks if not _unchanged(b)])
                redact_keeping_forms(page, areas)
                # A label OCR read from a picture (translation.figure_text): its ink is erased from
                # the picture the way a scanned page's is, and the translation drawn in its place.
                raster = [b for b in blocks if b.raster]
                if raster:
                    _cover_scanned_blocks(page, raster)
                if underlines:
                    redact_keeping_forms(page, underlines, line_art=True)
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
                    # The paper beside the line, offered to every role that reads left to right:
                    # widening a heading or a running header keeps its one line (which is what
                    # those roles protect), while room *below* is what wraps them. A table cell and
                    # a centred block are excluded (see `growth.may_grow_right`). The fitting pass
                    # granted exactly this much, from the same rule.
                    grant_right = (
                        free_right(block, everything, obstacles=pictures)
                        if not _unchanged(block) and may_grow_right(block)
                        else 0.0
                    )
                    rect = _layout_rect(block.bbox, room, grant, grant_right)
                    _draw_block(page, rect, html, css, resolver.archive)
        # `garbage=4` dedupes identical objects: every block drawn in a given resolved font
        # embeds its own copy of that font's subset bytes (`insert_htmlbox`'s own font-loading
        # does not share a face across separate calls, even given the same `archive`), and since
        # `_subset_font` produces byte-identical output for the same (font, characters) pair,
        # `garbage=4` collapses those duplicates back into one object at save time instead of
        # leaving 17 bundled fonts' worth of repeated subsets in the output.
        # Ne çevrildi, neyle: dosyanın kendisi söylesin diye kayıt burada yazılır (core/provenance.py).
        record = provenance.of(doc)
        if record:
            _write_provenance(pdf, record)
        pdf.save(str(out_path), garbage=4, deflate=True)
