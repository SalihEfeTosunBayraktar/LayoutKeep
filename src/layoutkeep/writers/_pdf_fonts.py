"""Font resolution: embedded source fonts, subsetting, variable weights, fallbacks.

Yazı tipi çözümleme: gömülü kaynak yazı tipleri, alt kümeleme, değişken ağırlık ve yedekler.
"""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass

import pymupdf
from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib.instancer import instantiateVariableFont

from layoutkeep.core.docir import Block, Style
from layoutkeep.core.hyphenate import soft_hyphens
from layoutkeep.fitting.fontmatch import FontMatch, MatchQuality, missing_glyphs, resolve_font
from layoutkeep.writers._pdf_writer_common import (
    _ALWAYS_KEEP_CHARS,
    _BASE14,
    _FONT_LOAD_ERRORS,
    _SUBSET_TAG_RE,
)


def _base14_font(style: Style) -> str:
    return _BASE14[(_generic_family(style.font_family, style.serif), style.bold, style.italic)]


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
        self._styles: dict[tuple[str, bool, bool], Style] = {}
        self._resolved: dict[tuple[str, bool, bool], _EmbeddedFont | None] = {}
        self._face_rules: list[str] = []
        self.archive = pymupdf.Archive()
        self._next_id = 0

    @property
    def target_lang(self) -> str:
        return self._target_lang

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
        if soft_hyphens(text, self._target_lang) != text:
            self._chars[key].add("-")  # drawn where a soft hyphen breaks a line
        if key in self._matches or key in self._preset_paths:
            return
        self._styles[key] = style
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
        for key, match in list(self._matches.items()):
            if match.quality is MatchQuality.ORIGINAL and self._subset_lacks_drawn_chars(key):
                match = self._substitute(key) or match
                self._matches[key] = match
            if match.quality is MatchQuality.ORIGINAL:
                raw = self._original_bytes.get(key)
                if raw is not None:
                    self._embed(key, raw)
                # else: covers_target was true but the bytes could not be re-extracted - leave
                # unresolved, the block falls back to the generic mapping.
            elif match.resolved_path:
                self._embed(key, (match.resolved_path, match.resolved_font_number))

    def _subset_lacks_drawn_chars(self, key: tuple[str, bool, bool]) -> bool:
        """Does the reused source subset miss a character this document draws in it?

        Resolution only checks the target language's letters outside ASCII, which is nothing for
        English: the Turkish Penal Code's Times New Roman subset, cut to Turkish letters, was reused
        for its English translation and every w, q and x came from another face. Here every
        character drawn in the face is known, so it is checked against the subset itself.
        """
        raw = self._original_bytes.get(key)
        drawn = "".join(c for c in self._chars.get(key, set()) if c.isprintable() and not c.isspace())
        if raw is None or not drawn:
            return False
        try:
            return bool(missing_glyphs(raw, drawn))
        except _FONT_LOAD_ERRORS:
            return True  # a subset whose coverage cannot be read is not trusted with new letters

    def _substitute(self, key: tuple[str, bool, bool]) -> FontMatch | None:
        """Resolve the style again as if the source had embedded nothing - a complete face."""
        style = self._styles.get(key)
        if style is None:
            return None
        try:
            return resolve_font(
                style.font_family or "sans-serif",
                self._target_lang,
                bold=style.bold,
                italic=style.italic,
                embedded_font_bytes=None,
                serif_hint=style.serif,
            )
        except _FONT_LOAD_ERRORS:
            return None

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
