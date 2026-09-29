"""The HTML/CSS a block is drawn from: spans, escaping, alignment.

Bloğun çizildiği HTML/CSS'i üretir: parçalar, kaçış karakterleri ve hizalama.
"""

from __future__ import annotations

import re

from layoutkeep.core import tunables
from layoutkeep.core.docir import Block, Span, Style
from layoutkeep.core.hyphenate import soft_hyphens
from layoutkeep.writers._pdf_fonts import _FontResolver
from layoutkeep.writers._pdf_writer_common import _INLINE_SPAN_SIZES_KEY


def _escape_text(text: str) -> str:
    # A control character is extraction noise - a symbol-font glyph with no mapping comes out as NUL
    # - and the HTML layout stops at a NUL, dropping the rest of the block while reporting a fit
    # (held-out PLOS ONE, page 13). It has no drawable form to keep.
    text = _CONTROL_CHARACTERS.sub("", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def span_markup(text: str, style: Style, dominant: Style) -> str:
    """One run's inline html: the escaping and the weight/size wrappers it is drawn inside.

    Split out of `_span_html` so the fitting pass can measure a translation as the page will show
    it. The family and colour wrappers `_span_html` adds on top need the writer's resolved fonts,
    which a measurement has no business resolving; what decides how much room a run takes - `<b>`,
    `<i>` and a run set smaller than its block - is here, in one place, so measure and draw cannot
    drift apart on it.
    """
    escaped = _escape_text(text)
    if not escaped:
        return ""
    # `<i>`/`<b>` are always applied from the span's own flags: MuPDF synthesizes slant/weight on a
    # face that does not have a dedicated italic/bold instance, which today's font matcher does not
    # always pick even when one is bundled (a separate, already-known `fontmatch.find_family`
    # limitation - see the PDF writer agent's report).
    if style.italic:
        escaped = f"<i>{escaped}</i>"
    if style.bold:
        escaped = f"<b>{escaped}</b>"
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
        escaped = f'<span style="font-size:{style.size:.2f}pt">{escaped}</span>'
    return escaped


def _span_html(span: Span, dominant: Style, resolver: _FontResolver) -> str:
    # Soft hyphens only here, in what is drawn (core/hyphenate.py): a long German word breaks
    # instead of shrinking its block. The fitting pass measures the same string.
    text = span_markup(soft_hyphens(span.text, resolver.target_lang), span.style, dominant)
    if not text:
        return ""
    style = span.style
    family = resolver.css_family_for(style)
    dominant_family = resolver.css_family_for(dominant)
    # Family and colour stay here: they come from the fonts the writer resolved, which are a
    # property of the page being written, not of the run.
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
