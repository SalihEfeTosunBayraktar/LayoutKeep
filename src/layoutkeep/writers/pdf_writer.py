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
import io
import math
import re
import string
from dataclasses import dataclass
from pathlib import Path

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

#: `insert_htmlbox`'s own line-height/padding model is not pixel-identical to the tight glyph
#: bbox `pdf_reader.py` measures, so even untouched text can be a point or two taller than its
#: source bbox, and the writer must let `insert_htmlbox` absorb that gap. It may not go further
#: than that: this is the same readability floor `fitting/` shrinks to (D3 is still fitting's
#: job), so the writer can no longer quietly undercut a decision fitting already made and
#: flagged. See `_draw_block` for what happens when the floor is not enough.
_WRITE_SCALE_LOW_KEY = "fit.min_scale"  # the writer shares fitting's floor
_BOX_SLACK_KEY = "write.box_slack_pt"

#: Below this many degrees a block is treated as ordinary horizontal text - noise in pymupdf's
#: `dir` vector, not an actual rotation. Matches `pdf_reader.py`'s own tolerance.
_ROTATION_EPS = 0.5
#: `insert_htmlbox`'s line-height guess, reused for stacking a rotated block's lines.
_LINE_HEIGHT_RATIO = 1.2

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


def write_pdf(doc: Document, src_path: str | Path, out_path: str | Path) -> None:
    """Render `doc` (read from `src_path`, possibly with translations applied) to `out_path`."""
    with pymupdf.open(str(src_path)) as pdf:
        resolver = _FontResolver(doc.target_lang)
        page_blocks: list[tuple[pymupdf.Page, list[Block]]] = []
        for page_data in doc.pages:
            page = pdf[int(page_data.source_ref)]
            blocks = [b for b in page_data.blocks if b.translatable]
            if not blocks:
                continue
            # Font resolution runs before any page is redacted: it may need to read the source
            # PDF's own embedded font bytes (`_extract_embedded_font_bytes`), and there is no
            # reason to depend on `apply_redactions` leaving font resources alone longer than
            # necessary.
            for block in blocks:
                resolver.register(page, block)
            page_blocks.append((page, blocks))
        resolver.finalize()

        for page, blocks in page_blocks:
            for block in blocks:
                if abs(block.rotation) > _ROTATION_EPS:
                    # A rotated line's axis-aligned bbox is bigger than its glyphs (see
                    # `Block.rotation`'s docstring); redacting that whole rectangle would eat
                    # into whatever sits in its corners. Redact the actual glyph quads instead.
                    for quad in _rotated_quads(page, block):
                        page.add_redact_annot(quad, cross_out=False, fill=None)
                else:
                    page.add_redact_annot(_rect(block.bbox), cross_out=False, fill=None)
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_NONE,
                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            )
            for block in blocks:
                if abs(block.rotation) > _ROTATION_EPS:
                    _write_rotated_block(page, block, resolver)
                else:
                    html = f"<p>{_block_html(block, resolver)}</p>"
                    css = _css_for_block(block, resolver)
                    _draw_block(page, _layout_rect(block.bbox), html, css, resolver.archive)
        # `garbage=4` dedupes identical objects: every block drawn in a given resolved font
        # embeds its own copy of that font's subset bytes (`insert_htmlbox`'s own font-loading
        # does not share a face across separate calls, even given the same `archive`), and since
        # `_subset_font` produces byte-identical output for the same (font, characters) pair,
        # `garbage=4` collapses those duplicates back into one object at save time instead of
        # leaving 17 bundled fonts' worth of repeated subsets in the output.
        pdf.save(str(out_path), garbage=4, deflate=True)


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
            return spare != -1, scale
        finally:
            scratch.close()

    lines = text.split("\n") or [""]
    font = _measure_rotated_font(style)
    steps = 16
    for i in range(steps + 1):
        scale = 1.0 - (1.0 - scale_low) * i / steps
        size = style.size * scale
        longest = max((font.text_length(ln, fontsize=size) for ln in lines), default=0.0)
        depth = len(lines) * size * _LINE_HEIGHT_RATIO
        if rotated_block_fits(bbox, rotation, longest, depth):
            return True, scale
    return False, scale_low


def _measure_horizontal_source(style: Style) -> tuple[str, pymupdf.Archive | None]:
    """CSS family name plus a matching one-file `Archive` when `style.font_path` is set, else
    the old generic-family keyword with no archive at all."""
    if style.font_path:
        return "MeasureFont", pymupdf.Archive(style.font_path, "measure.ttf")
    return _generic_family(style.font_family), None


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
    spare, _scale = page.insert_htmlbox(
        rect, html, css=css, scale_low=min_scale_setting(), archive=archive
    )
    if spare < 0:
        page.insert_htmlbox(rect, html, css=css, scale_low=0, archive=archive)


def _layout_rect(bbox: BBox) -> pymupdf.Rect:
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
    return pymupdf.Rect(rect.x0, rect.y0, rect.x1 + slack, rect.y1 + slack)


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
    return quads or [pymupdf.Quad(clip)]


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
    return found or runs or [pymupdf.Quad(line_rect)]


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
    return _BASE14[(_generic_family(style.font_family), style.bold, style.italic)]


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
    line_height = dominant.size * _LINE_HEIGHT_RATIO
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
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _generic_family(font_name: str) -> str:
    """Map a source PDF font name to one of the generic families pymupdf's HTML engine always
    knows, without needing a resolved font file. Fallback for blocks `_FontResolver` could not
    resolve to a real font file at all."""
    lowered = font_name.lower()
    if any(k in lowered for k in ("courier", "mono", "consolas")):
        return "monospace"
    if any(k in lowered for k in ("times", "georgia", "serif", "garamond", "cambria", "minion")):
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
    return (
        f"{resolver.css_face_rules()} "
        f"p {{ font-family: {family}; font-size: {dominant.size:.2f}pt; color: {dominant.color}; "
        f"direction: {block.direction.value}; margin: 0; }}"
    )


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
        return resolved.css_family if resolved else _generic_family(style.font_family)

    def font_bytes_for(self, style: Style) -> bytes | None:
        resolved = self._resolved.get(_style_key(style))
        return resolved.font_bytes if resolved else None
