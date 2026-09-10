"""Font resolution: map an original (often subsetted) font name to a real, glyph-complete font.

See docs/CONTRACT.md D1/D2: this module never imports PyMuPDF. It reads font files directly
with fontTools (name/cmap/OS2/hmtx/glyf tables) so glyph coverage and metrics are *measured*,
never assumed.

Why substitution is usually unavoidable: PDF embedded fonts are subsetted to only the glyphs the
source document actually used. English source text rarely used `ğ ş İ ı`, `ß` or `ł`, so the
embedded font's cmap is missing them even though its *name* says "Arial" or "Times New Roman".
`resolve_font()` checks this when given the embedded font's bytes; it does not guess.
"""

from __future__ import annotations

import io
import os
import re
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont, TTLibError

# --------------------------------------------------------------------------------------
# Per-language glyph requirements
#
# Only the characters outside plain ASCII that are common enough in the language's ordinary
# orthography to appear in translated text and break a subsetted source font.
# --------------------------------------------------------------------------------------

REQUIRED_GLYPHS: dict[str, str] = {
    "tr": "ğĞşŞıİçÇöÖüÜ",
    "de": "äöüßÄÖÜ",
    "pl": "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "fr": "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ",
    "es": "áéíóúñüÁÉÍÓÚÑÜ¿¡",
    "it": "àèéìòóùÀÈÉÌÒÓÙ",
    "pt": "áâãàçéêíóôõúÁÂÃÀÇÉÊÍÓÔÕÚ",
    "nl": "éëïöüÉËÏÖÜ",
}


class FontClass(StrEnum):
    """Coarse visual family - the classification fallback the brief asks for."""

    SERIF = "serif"
    SANS = "sans"
    MONO = "mono"
    UNKNOWN = "unknown"


#: Metric-compatible substitution table, keyed by normalized original family name.
SUBSTITUTION_TABLE: dict[str, str] = {
    "timesnewroman": "Tinos",
    "times": "Tinos",
    "arial": "Arimo",
    "helvetica": "Arimo",
    "couriernew": "Cousine",
    "courier": "Cousine",
    "cambria": "Caladea",
    "calibri": "Carlito",
}

#: Fallback substitute family per classification, used when the name isn't in the table above.
CLASS_FALLBACK: dict[FontClass, str] = {
    FontClass.SERIF: "Noto Serif",
    FontClass.SANS: "Noto Sans",
    FontClass.MONO: "Cousine",
}

#: Normalized name -> canonical registry family name, for the fonts LayoutKeep itself bundles
#: (see `assets/fonts/README.md`). `SUBSTITUTION_TABLE` maps *source* names onto these; this
#: table is the missing other half - recognising when the source already names one of them, so
#: a document already set in Arimo or Tinos resolves to the exact verified file instead of
#: falling through to a classification guess.
BUNDLED_FAMILIES: dict[str, str] = {
    "arimo": "Arimo",
    "tinos": "Tinos",
    "cousine": "Cousine",
    "caladea": "Caladea",
    "carlito": "Carlito",
    "notosans": "Noto Sans",
    "notoserif": "Noto Serif",
}

_SERIF_HINTS = (
    "times", "georgia", "cambria", "garamond", "serif", "minion", "caladea", "tinos",
    "palatino", "constantia", "book",
)
_SANS_HINTS = (
    "arial", "helvetica", "calibri", "verdana", "tahoma", "segoe", "sans", "arimo",
    "carlito", "roboto", "opensans",
)
_MONO_HINTS = ("courier", "consolas", "mono", "cousine")

#: ISO 32000 requires exactly six uppercase Latin letters, but non-conforming producers (some
#: PDF mergers, re-savers) emit digits in the tag too, or leave a second tag behind when a
#: subset gets re-subsetted downstream - so this strips repeatedly, not just once, and accepts
#: digits alongside letters.
_SUBSET_TAG_RE = re.compile(r"^[A-Z0-9]{6}\+")


def _strip_subset_tag(name: str) -> str:
    """"ABCDEF+Times-BoldItalicMT" -> "Times-BoldItalicMT": strip one or more leading PDF subset tags."""
    while True:
        stripped = _SUBSET_TAG_RE.sub("", name, count=1)
        if stripped == name:
            return name
        name = stripped


def _normalize(name: str) -> str:
    """"ABCDEF+Times-BoldItalicMT" -> "timesbolditalicmt": strip the PDF subset tag(s) and case."""
    return re.sub(r"[^a-z]", "", _strip_subset_tag(name).lower())


def classify(name: str) -> FontClass:
    """Classify a font by family name when it isn't in `SUBSTITUTION_TABLE`.

    This catches most real-world cases: serif/sans/mono plus weight and slant (checked
    separately by `is_bold`/`is_italic`) account for the large majority of substitutions.
    """
    n = _normalize(name)
    if any(h in n for h in _MONO_HINTS):
        return FontClass.MONO
    # Sans is tested before serif on purpose: "serif" is a substring of "sans-serif", so the
    # other order classifies the generic CSS family "sans-serif" as SERIF and picks the wrong
    # typeface for every block a writer passes a generic family name for.
    if any(h in n for h in _SANS_HINTS):
        return FontClass.SANS
    if any(h in n for h in _SERIF_HINTS):
        return FontClass.SERIF
    return FontClass.UNKNOWN


def _match_bundled_family(normalized: str) -> str | None:
    """Look up `normalized` against `BUNDLED_FAMILIES` by substring, the same way `classify()`
    matches its hint lists - a real-world PostScript name is "arimoregular" or "arimobolditalic",
    never the bare "arimo" that a dict-key equality check would require."""
    for key, family in sorted(BUNDLED_FAMILIES.items(), key=lambda kv: -len(kv[0])):
        if key in normalized:
            return family
    return None


def is_bold(name: str) -> bool:
    return bool(re.search(r"bold|black|heavy", name, re.IGNORECASE))


def is_italic(name: str) -> bool:
    return bool(re.search(r"italic|oblique", name, re.IGNORECASE))


# --------------------------------------------------------------------------------------
# Font metrics and glyph coverage - real, measured values via fontTools
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class FontMetrics:
    """Metrics as a fraction of em size, so fonts at different sizes/unitsPerEm compare directly."""

    units_per_em: int
    x_height: float
    cap_height: float
    avg_advance: float  # mean advance width of the lowercase ASCII alphabet


def _open_ttfont(source: str | bytes | Path, font_number: int = 0) -> TTFont:
    if isinstance(source, bytes):
        return TTFont(io.BytesIO(source), fontNumber=font_number, lazy=True)
    path = str(source)
    if path.lower().endswith(".ttc"):
        return TTCollection(path, lazy=True).fonts[font_number]
    return TTFont(path, fontNumber=font_number, lazy=True)


def read_metrics(source: str | bytes | Path, font_number: int = 0) -> FontMetrics:
    """Measure x-height, cap-height and average lowercase advance width from an actual font.

    Uses the OS/2 table's `sxHeight`/`sCapHeight` when present (TrueType/OpenType OS/2 v2+);
    otherwise falls back to the real glyph bounding box of 'x' and 'H' via the glyf/CFF outline,
    which is exact, not estimated.
    """
    font = _open_ttfont(source, font_number)
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()

    x_height = _table_or_bbox_height(font, cmap, glyph_set, "x", upm)
    cap_height = _table_or_bbox_height(font, cmap, glyph_set, "H", upm)

    hmtx = font["hmtx"]
    widths = []
    for ch in "abcdefghijklmnopqrstuvwxyz":
        gname = cmap.get(ord(ch))
        if gname is not None:
            widths.append(hmtx[gname][0])
    avg_advance = (sum(widths) / len(widths) / upm) if widths else 0.0

    return FontMetrics(
        units_per_em=upm,
        x_height=x_height,
        cap_height=cap_height,
        avg_advance=avg_advance,
    )


def _table_or_bbox_height(font: TTFont, cmap: dict[int, str], glyph_set, char: str, upm: int) -> float:
    os2 = font.get("OS/2")
    field_name = "sxHeight" if char == "x" else "sCapHeight"
    if os2 is not None and os2.version >= 2:
        value = getattr(os2, field_name, 0)
        if value:
            return value / upm
    gname = cmap.get(ord(char))
    if gname is None:
        return 0.0
    from fontTools.pens.boundsPen import BoundsPen

    pen = BoundsPen(glyph_set)
    glyph_set[gname].draw(pen)
    if pen.bounds is None:
        return 0.0
    _, _, _, y_max = pen.bounds
    return y_max / upm


def missing_glyphs(source: str | bytes | Path, chars: str, font_number: int = 0) -> str:
    """Return the subset of `chars` this font's cmap does NOT contain.

    This is the coverage check the brief demands before assuming a font can be reused as-is:
    an empty return means every requested character is present.
    """
    if not chars:
        return ""
    font = _open_ttfont(source, font_number)
    cmap = font.getBestCmap() or {}
    return "".join(c for c in chars if ord(c) not in cmap)


def metric_delta(resolved: FontMetrics, original: FontMetrics) -> dict[str, float]:
    """Relative difference (resolved - original) / original for each metric, so substitution
    quality is a number, not a claim."""

    def rel(a: float, b: float) -> float:
        return (a - b) / b if b else 0.0

    return {
        "x_height": rel(resolved.x_height, original.x_height),
        "cap_height": rel(resolved.cap_height, original.cap_height),
        "avg_advance": rel(resolved.avg_advance, original.avg_advance),
    }


# --------------------------------------------------------------------------------------
# Installed font registry
# --------------------------------------------------------------------------------------

DEFAULT_FONT_DIRS: tuple[str, ...] = (
    r"C:\Windows\Fonts",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".local/share/fonts"),
    "/System/Library/Fonts",
    "/Library/Fonts",
)

_FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")


@lru_cache(maxsize=1)
def _bundled_font_dir() -> str | None:
    """Locate the `assets/fonts` directory bundled with LayoutKeep (see `assets/fonts/README.md`).

    These are the fonts a substitution actually needs: metric-compatible for the Microsoft
    families, and verified to carry Turkish/German/Polish/etc glyphs that PDF-embedded subsets
    usually lack. Candidates are tried in order and the first one that actually contains font
    files wins - three deployment shapes need three different answers:

    1. PyInstaller bundle: data files land under `sys._MEIPASS` (see `packaging/layoutkeep.spec`,
       which copies `assets/fonts` there). This is the case that silently breaks in production
       and never in development, since `_MEIPASS` doesn't exist outside a frozen build.
    2. Installed package: if `assets/fonts` is shipped as package data next to the `layoutkeep`
       package (site-packages/layoutkeep/assets/fonts).
    3. Source tree: `assets/fonts` sits at the repo root, a sibling of `src/`.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "fonts")
    this_file = Path(__file__).resolve()
    candidates.append(this_file.parents[1] / "assets" / "fonts")  # installed: site-packages/layoutkeep/assets/fonts
    candidates.append(this_file.parents[3] / "assets" / "fonts")  # source tree: repo-root/assets/fonts

    for candidate in candidates:
        try:
            if candidate.is_dir() and any(candidate.glob("*.ttf")):
                return str(candidate)
        except OSError:
            continue
    return None


def _is_bundled(path: str) -> bool:
    """Whether `path` resolved from the bundled `assets/fonts` directory rather than the system."""
    bundled = _bundled_font_dir()
    if not bundled:
        return False
    try:
        Path(path).resolve().relative_to(Path(bundled).resolve())
        return True
    except ValueError:
        return False


@dataclass(slots=True)
class FontFile:
    path: str
    font_number: int
    family: str
    bold: bool
    italic: bool
    font_class: FontClass


class FontRegistry:
    """Indexes installed font files by family name so substitutes can actually be located.

    Building the index reads every font file's `name` table once; construction can take a
    noticeable moment with hundreds of system fonts, so keep one instance around rather than
    creating it per lookup (see `default_registry()`).
    """

    def __init__(self, font_dirs: list[str] | None = None):
        if font_dirs is not None:
            # Caller wants exactly these directories (used by tests to build a controlled
            # registry) - do not silently add the bundled fonts on top.
            raw_dirs = font_dirs
        else:
            # Default search order: bundled fonts first, so a known glyph-complete Tinos wins
            # over a system font that merely classifies as serif, then the system directories.
            bundled = _bundled_font_dir()
            raw_dirs = ([bundled] if bundled else []) + list(DEFAULT_FONT_DIRS)
        self._dirs = [d for d in raw_dirs if d and Path(d).is_dir()]
        self._files: list[FontFile] = []
        self._scan()

    def _scan(self) -> None:
        for d in self._dirs:
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(_FONT_EXTENSIONS):
                    self._index_file(entry.path)

    def _index_file(self, path: str) -> None:
        try:
            if path.lower().endswith(".ttc"):
                fonts = TTCollection(path, lazy=True).fonts
            else:
                fonts = [TTFont(path, lazy=True)]
        except (TTLibError, OSError):
            return
        for i, font in enumerate(fonts):
            try:
                name_table = font["name"]
                family = name_table.getDebugName(1) or name_table.getDebugName(16) or Path(path).stem
                subfamily = name_table.getDebugName(2) or name_table.getDebugName(17) or ""
                macstyle = font["head"].macStyle
                bold = bool(macstyle & 0x1) or is_bold(subfamily)
                italic = bool(macstyle & 0x2) or is_italic(subfamily)
                fclass = classify(family)
            except (KeyError, TTLibError):
                continue
            self._files.append(FontFile(path, i, family, bold, italic, fclass))

    def find_family(self, family: str, *, bold: bool = False, italic: bool = False) -> FontFile | None:
        """Exact-ish family match (case-insensitive substring), preferring the static file whose
        own weight/slant matches `bold`/`italic`."""
        target = family.strip().lower()
        candidates = [f for f in self._files if f.family.strip().lower() == target]
        if not candidates:
            candidates = [f for f in self._files if target in f.family.strip().lower()]
        return self._pick(candidates, bold=bold, italic=italic)

    def find_by_class(self, font_class: FontClass, *, bold: bool, italic: bool) -> FontFile | None:
        candidates = [f for f in self._files if f.font_class == font_class]
        return self._pick(candidates, bold=bold, italic=italic)

    @staticmethod
    def _pick(candidates: list[FontFile], *, bold: bool, italic: bool) -> FontFile | None:
        if not candidates:
            return None
        exact = [f for f in candidates if f.bold == bold and f.italic == italic]
        if exact:
            return exact[0]
        if not bold and not italic:
            return candidates[0]
        # No static file has the exact weight+slant. Several bundled families (Arimo, Noto
        # Sans/Serif) ship as variable fonts with no static Bold file at all - the registry
        # only indexes the file's own (regular) macStyle, it does not instance the `wght` axis
        # itself. That instancing is the caller's job (lk-pdf already does it with
        # fontTools.varLib.instancer when it embeds the resolved file), so the best this
        # registry can do is hand back the closest real file. Italic slant is prioritized over
        # bold weight when only one can be matched: a weight axis can often be pushed toward
        # bold by the caller, but italic requires genuinely different outlines that no amount
        # of instancing a non-italic file will produce.
        return max(candidates, key=lambda f: (f.italic == italic, f.bold == bold))


@lru_cache(maxsize=1)
def default_registry() -> FontRegistry:
    """Lazily-built, process-wide registry over the default system font directories."""
    return FontRegistry()


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------


class MatchQuality(StrEnum):
    """How much to trust a `FontMatch` - these are three different quality levels, not one.

    ORIGINAL:   the source PDF's own embedded font already has the needed glyphs. Best case,
                no substitution risk at all.
    BUNDLED:    the original name already names one of the fonts LayoutKeep ships and verified
                for the target language's glyph coverage (`BUNDLED_FAMILIES`). Not a guess and
                not a substitution - it's the exact file, matched by its own name.
    SUBSTITUTE: a metric-compatible replacement from `SUBSTITUTION_TABLE` was found (normally
                one of the bundled fonts in `assets/fonts`). Advance widths match the original
                family, so line breaks should hold.
    FALLBACK:   no metric-compatible substitute was available; a font was chosen only by visual
                classification (serif/sans/mono + weight/slant). Glyphs will be present but line
                widths may differ from the original - treat fitting results with more suspicion.
    NONE:       nothing could be resolved at all.
    """

    ORIGINAL = "original"
    BUNDLED = "bundled"
    SUBSTITUTE = "substitute"
    FALLBACK = "fallback"
    NONE = "none"


@dataclass(slots=True)
class FontMatch:
    original_name: str
    resolved_family: str
    resolved_path: str | None
    resolved_font_number: int
    font_class: FontClass
    quality: MatchQuality
    reason: str
    #: True/False if `embedded_font_bytes` was given and checked; None if it wasn't.
    original_covers_target: bool | None
    missing_in_original: str
    metrics: FontMetrics | None
    original_metrics: FontMetrics | None
    metric_delta: dict[str, float] = field(default_factory=dict)


def resolve_font(
    original_name: str,
    target_lang: str,
    *,
    bold: bool = False,
    italic: bool = False,
    embedded_font_bytes: bytes | None = None,
    serif_hint: bool | None = None,
    registry: FontRegistry | None = None,
) -> FontMatch:
    """Resolve `original_name` to a font file that can render `target_lang` text.

    If `embedded_font_bytes` is given (the actual embedded font extracted from the source PDF),
    its cmap is checked against `REQUIRED_GLYPHS[target_lang]`; a font that already covers them
    is reported as reusable instead of being substituted. Without the bytes, coverage is unknown
    and substitution is always applied, per the brief's rule not to assume subset fonts are complete.

    `serif_hint` is what the source document said about this run - `Style.serif`, which for a PDF
    comes off the font descriptor. It is consulted only when the family name classifies as
    UNKNOWN, which is where it does the work: a display face such as "AbrilFatface" is in no hint
    list and no substitution table, so without it every unrecognised serif is answered with a
    sans. A name we do recognise always wins, since producers set that flag carelessly.
    """
    reg = registry if registry is not None else default_registry()
    required = REQUIRED_GLYPHS.get(target_lang, "")
    bold = bold or is_bold(original_name)
    italic = italic or is_italic(original_name)

    original_metrics: FontMetrics | None = None
    missing = ""
    covers: bool | None = None
    if embedded_font_bytes is not None:
        original_metrics = read_metrics(embedded_font_bytes)
        missing = missing_glyphs(embedded_font_bytes, required)
        covers = not missing
        if covers:
            return FontMatch(
                original_name=original_name,
                resolved_family=original_name,
                resolved_path=None,
                resolved_font_number=0,
                font_class=classify(original_name),
                quality=MatchQuality.ORIGINAL,
                reason="original embedded font already covers the target language's glyphs; no substitution needed",
                original_covers_target=True,
                missing_in_original="",
                metrics=original_metrics,
                original_metrics=original_metrics,
                metric_delta={},
            )

    normalized = _normalize(original_name)
    table_family = SUBSTITUTION_TABLE.get(normalized)
    fclass = classify(original_name)
    if fclass is FontClass.UNKNOWN and serif_hint is not None:
        fclass = FontClass.SERIF if serif_hint else FontClass.SANS

    found: FontFile | None = None
    reason = ""
    quality = MatchQuality.NONE

    bundled_family = _match_bundled_family(normalized)
    if bundled_family:
        candidate = reg.find_family(bundled_family, bold=bold, italic=italic)
        # Only trust this as "the exact bundled font" if it actually came from the bundled
        # directory - a same-named but unrelated system font wouldn't carry the verified
        # target-language coverage this quality level promises.
        if candidate and _is_bundled(candidate.path):
            found = candidate
            quality = MatchQuality.BUNDLED
            reason = (
                f"{original_name!r} already names a bundled font ({bundled_family}); "
                "using it directly, no substitution needed"
            )

    if found is None and table_family:
        found = reg.find_family(table_family, bold=bold, italic=italic)
        if found:
            origin = "bundled" if _is_bundled(found.path) else "system"
            quality = MatchQuality.SUBSTITUTE
            reason = f"metric-compatible substitution: {original_name!r} -> {table_family} ({origin})"
        else:
            reason = f"substitution table wants {table_family!r} but it is not installed"
    if found is None and fclass is not FontClass.UNKNOWN:
        fallback_family = CLASS_FALLBACK.get(fclass, "")
        if fallback_family:
            found = reg.find_family(fallback_family, bold=bold, italic=italic)
            if found:
                origin = "bundled" if _is_bundled(found.path) else "system"
                quality = MatchQuality.FALLBACK
                reason = (
                    (reason + "; " if reason else "")
                    + f"classification fallback: no name match, classified as {fclass.value}, "
                    f"using {fallback_family} ({origin})"
                )
    if found is None:
        # Last resort: any installed font of the right class/weight/slant actually present.
        # A bundled fallback (Noto Sans/Serif, or one of the other bundled families) is normally
        # what turns up here, since `FontRegistry` searches the bundled directory first - so this
        # is a real match, not an empty-handed guess, even though neither the name nor the
        # `CLASS_FALLBACK` table pointed at it directly.
        found = reg.find_by_class(fclass if fclass is not FontClass.UNKNOWN else FontClass.SANS, bold=bold, italic=italic)
        if found:
            quality = MatchQuality.FALLBACK
            reason = (
                (reason + "; " if reason else "")
                + f"classification fallback: no name or class-based substitute configured for "
                f"{original_name!r}, used nearest installed {found.font_class.value} match: {found.family}"
            )

    if found is None:
        return FontMatch(
            original_name=original_name,
            resolved_family="",
            resolved_path=None,
            resolved_font_number=0,
            font_class=fclass,
            quality=MatchQuality.NONE,
            reason=reason or "no installed font matches this family or class",
            original_covers_target=covers,
            missing_in_original=missing,
            metrics=None,
            original_metrics=original_metrics,
            metric_delta={},
        )

    resolved_metrics = read_metrics(found.path, found.font_number)
    delta = metric_delta(resolved_metrics, original_metrics) if original_metrics else {}
    return FontMatch(
        original_name=original_name,
        resolved_family=found.family,
        resolved_path=found.path,
        resolved_font_number=found.font_number,
        font_class=found.font_class,
        quality=quality,
        reason=reason,
        original_covers_target=covers,
        missing_in_original=missing,
        metrics=resolved_metrics,
        original_metrics=original_metrics,
        metric_delta=delta,
    )
