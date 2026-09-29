"""Measuring whether a translation fits its box, and the rectangle it is laid out in.

Çevirinin kutusuna sığıp sığmadığını ölçer ve metnin yerleşeceği dikdörtgeni hesaplar.
"""

from __future__ import annotations

import html as html_escapes
import re
import unicodedata

import pymupdf

from layoutkeep.core import tunables
from layoutkeep.core.docir import BBox, Style
from layoutkeep.fitting import rotated_block_fits
from layoutkeep.writers._pdf_fonts import _base14_font, _generic_family
from layoutkeep.writers._pdf_markup import _escape_text
from layoutkeep.writers._pdf_writer_common import (
    _BOX_SLACK_KEY,
    _ROTATION_EPS,
    _rect,
    writer_line_height_ratio,
)


def measure_fit(
    text: str,
    style: Style,
    bbox: BBox,
    *,
    scale_low: float = 0.85,
    rotation: float = 0.0,
    markup: bool = False,
) -> tuple[bool, float]:
    """Check whether `text` rendered in `style` fits `bbox`. The seam `fitting/` calls through -
    it never imports pymupdf itself.

    Returns `(fits, scale)`. `fits` is False when even shrinking down to `scale_low` is not
    enough (mirrors `insert_htmlbox`'s `spare_height == -1`). Runs against a private scratch
    document, so it never touches the document being translated.

    `markup=True` says `text` is already html (`span_markup`, one fragment per run) and must be laid
    out as it stands instead of being escaped - inside the same `<p>` wrapper the writer builds in
    `write_pdf`. The wrapper is not decoration: drop it and the renderer never applies the
    `p { font-size: ... }` rule, lays the text out at its own default size and the same box reports
    "does not fit" (measured on NIST JR img0#44: 8.95pt in its own 13.2pt box fits at 0.88 with the
    wrapper, does not fit at all without it).

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
            html = f"<p>{text if markup else _escape_text(text)}</p>"
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
    bbox: BBox, room_below: float | None = None, grant_below: float = 0.0,
    grant_right: float = 0.0,
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

    `grant_right` is the paper the page has beside the block (`fitting.growth.free_right`), which
    the fitting pass measured against: the tight box is one line tall, so a longer translation
    that may reach into the empty paper beside it stays one line instead of wrapping into a line
    the box has no height for - or being shrunk to the floor to avoid it. Same number on both
    sides, for the reason `room_below` is shared: two rules drift, one cannot.
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
    return pymupdf.Rect(rect.x0, rect.y0, rect.x1 + slack + max(0.0, grant_right), bottom)


#: The least height a block is drawn in, whatever overlaps it from below.
_MIN_DRAW_HEIGHT = 6.0
