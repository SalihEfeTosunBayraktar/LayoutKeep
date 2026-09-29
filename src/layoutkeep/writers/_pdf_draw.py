"""Drawing a translated block onto the page, rotated text and searchable quads included.

Çevrilmiş bloğu sayfaya çizer; döndürülmüş metin ve aranabilir dörtgenler dahil.
"""

from __future__ import annotations

import math
import re

import pymupdf

from layoutkeep.core import tunables
from layoutkeep.core.docir import Block
from layoutkeep.fitting.fit import min_scale_setting
from layoutkeep.writers._pdf_fonts import _base14_font, _FontResolver
from layoutkeep.writers._pdf_measure import _lays_out_whole
from layoutkeep.writers._pdf_writer_common import _ROTATION_EPS, _rect, writer_line_height_ratio


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
