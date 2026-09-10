"""Font resolution tests: classification, glyph coverage on a real subsetted font, and
substitution against a controlled registry (so results don't depend on what happens to be
installed beyond the Windows-standard fonts this repo's dev environment ships with)."""

from __future__ import annotations

import io
import os

import pytest

pytest.importorskip("fontTools")
from fontTools import subset
from fontTools.ttLib import TTFont

from layoutkeep.fitting.fontmatch import (
    BUNDLED_FAMILIES,
    FontClass,
    FontRegistry,
    MatchQuality,
    classify,
    default_registry,
    is_bold,
    is_italic,
    missing_glyphs,
    read_metrics,
    resolve_font,
)

WIN_FONTS = r"C:\Windows\Fonts"
ARIAL = os.path.join(WIN_FONTS, "arial.ttf")
TIMES = os.path.join(WIN_FONTS, "times.ttf")
COURIER = os.path.join(WIN_FONTS, "cour.ttf")

pytestmark = pytest.mark.skipif(
    not all(os.path.isfile(p) for p in (ARIAL, TIMES, COURIER)),
    reason="standard Windows fonts not present on this system",
)


def _ascii_only_subset(path: str) -> bytes:
    """Simulate a PDF-embedded subset font: only the ASCII glyphs the source text used."""
    font = TTFont(path)
    options = subset.Options()
    options.glyph_names = False
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=[ord(c) for c in (chr(i) for i in range(0x20, 0x7F))])
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Times New Roman", FontClass.SERIF),
        ("ABCDEF+Cambria-Bold", FontClass.SERIF),
        ("Arial-BoldMT", FontClass.SANS),
        ("Helvetica", FontClass.SANS),
        ("Courier New", FontClass.MONO),
        ("Consolas", FontClass.MONO),
        ("SomeRandomFontXYZ", FontClass.UNKNOWN),
    ],
)
def test_classify(name, expected):
    assert classify(name) == expected


def test_is_bold_and_italic_from_name():
    assert is_bold("Arial-BoldMT") is True
    assert is_bold("Arial") is False
    assert is_italic("Times-Italic") is True
    assert is_italic("Times") is False


# --------------------------------------------------------------------------------------
# Glyph coverage - the core "don't assume, check" behaviour
# --------------------------------------------------------------------------------------


def test_full_font_covers_turkish_glyphs():
    missing = missing_glyphs(ARIAL, "ğĞşŞıİ")
    assert missing == ""


def test_ascii_subset_is_missing_turkish_glyphs():
    subset_bytes = _ascii_only_subset(ARIAL)
    missing = missing_glyphs(subset_bytes, "ğĞşŞıİ")
    assert missing == "ğĞşŞıİ"  # none of these survived the ASCII-only subset


def test_ascii_subset_still_has_plain_ascii():
    subset_bytes = _ascii_only_subset(ARIAL)
    assert missing_glyphs(subset_bytes, "ABCabc") == ""


# --------------------------------------------------------------------------------------
# Metrics - real measured numbers, not estimates
# --------------------------------------------------------------------------------------


def test_read_metrics_reports_positive_measured_values():
    m = read_metrics(ARIAL)
    assert m.units_per_em == 2048
    assert 0 < m.x_height < 1
    assert 0 < m.cap_height < 1
    assert m.cap_height > m.x_height  # cap height is always taller than x-height
    assert m.avg_advance > 0


# --------------------------------------------------------------------------------------
# Resolution against a controlled registry
# --------------------------------------------------------------------------------------


@pytest.fixture()
def limited_registry(tmp_path):
    """A registry that only knows about standard Windows fonts - Tinos/Arimo/Noto are NOT
    installed here, so resolution must fall back to classification instead of silently
    pretending the table's first choice exists."""
    import shutil

    for src in (ARIAL, TIMES, COURIER):
        shutil.copy(src, tmp_path / os.path.basename(src))
    return FontRegistry(font_dirs=[str(tmp_path)])


def test_registry_finds_installed_family_by_name(limited_registry):
    found = limited_registry.find_family("Arial")
    assert found is not None
    assert found.font_class == FontClass.SANS


def test_registry_returns_none_for_family_not_installed(limited_registry):
    assert limited_registry.find_family("Tinos") is None


def test_resolve_falls_back_to_classification_when_table_target_missing(limited_registry):
    match = resolve_font("Times New Roman", "tr", registry=limited_registry)
    # Tinos (the table's first choice) isn't installed in this controlled registry, and neither
    # is the classification fallback (Noto Serif) - so it must fall through to "nearest serif
    # font actually installed" rather than silently claiming Tinos was used.
    assert match.resolved_path is not None
    assert match.font_class == FontClass.SERIF
    assert "not installed" in match.reason or "no configured substitute" in match.reason


def test_resolve_reports_glyph_coverage_when_given_embedded_bytes(limited_registry):
    subset_bytes = _ascii_only_subset(ARIAL)
    match = resolve_font(
        "Arial", "tr", registry=limited_registry, embedded_font_bytes=subset_bytes
    )
    assert match.original_covers_target is False
    assert match.missing_in_original != ""
    assert match.resolved_path is not None  # still resolves to a substitute


def test_resolve_reuses_original_when_it_already_covers_target(limited_registry):
    with open(ARIAL, "rb") as f:
        full_bytes = f.read()
    match = resolve_font("Arial", "tr", registry=limited_registry, embedded_font_bytes=full_bytes)
    assert match.original_covers_target is True
    assert match.resolved_path is None
    assert match.missing_in_original == ""


def test_resolve_computes_metric_delta_against_original(limited_registry):
    subset_bytes = _ascii_only_subset(TIMES)
    match = resolve_font(
        "Times New Roman", "tr", registry=limited_registry, embedded_font_bytes=subset_bytes
    )
    assert match.original_metrics is not None
    assert match.metrics is not None
    assert set(match.metric_delta) == {"x_height", "cap_height", "avg_advance"}


def test_resolve_reports_when_nothing_matches(tmp_path):
    empty_registry = FontRegistry(font_dirs=[str(tmp_path)])
    match = resolve_font("Times New Roman", "tr", registry=empty_registry)
    assert match.resolved_path is None
    assert match.reason  # must explain why, not fail silently


# --------------------------------------------------------------------------------------
# Bundled families - the source name already IS one of ours (regression: previously fell
# through to a classification guess even though the exact file is right there)
# --------------------------------------------------------------------------------------

_bundled_registry = default_registry()

pytestmark_bundled = pytest.mark.skipif(
    _bundled_registry.find_family("Arimo") is None,
    reason="bundled assets/fonts directory not found in this environment",
)


@pytestmark_bundled
@pytest.mark.parametrize("normalized_key,family", list(BUNDLED_FAMILIES.items()))
@pytest.mark.parametrize("prefix", ["", "ABCDEF+"])
def test_resolve_recognizes_bundled_family_by_name(normalized_key, family, prefix):
    original_name = f"{prefix}{family.replace(' ', '')}-Regular"
    match = resolve_font(original_name, "tr")
    assert match.quality == MatchQuality.BUNDLED
    assert match.resolved_family == family
    assert match.resolved_path is not None


@pytestmark_bundled
def test_resolve_unknown_embedded_font_lands_on_bundled_fallback():
    match = resolve_font("CAGenerated", "tr")
    assert match.resolved_path is not None
    assert match.quality == MatchQuality.FALLBACK
    assert "no configured substitute installed" not in match.reason


# --------------------------------------------------------------------------------------
# Bold/italic selection - regression for `find_family()` not accepting a requested style
# (it used to hard-code bold=False, italic=False and could not even take the keywords).
# Assertions read the resolved file's own macStyle bit, never its filename, since a
# filename can lie about what's actually inside.
# --------------------------------------------------------------------------------------


def _macstyle(path: str, font_number: int = 0) -> int:
    font = TTFont(path, fontNumber=font_number, lazy=True)
    return font["head"].macStyle


# Families that ship a real static Bold and a real static Italic file (see
# assets/fonts/README.md): Caladea/Carlito/Cousine have Bold + Italic but no BoldItalic,
# Tinos has all four. Arimo/Noto Sans/Noto Serif are excluded here - they are variable
# fonts with no static Bold file at all (see the variable-family test below).
_STATIC_STYLED_FAMILIES = ["Tinos", "Caladea", "Carlito", "Cousine"]


@pytestmark_bundled
@pytest.mark.parametrize("family", _STATIC_STYLED_FAMILIES)
def test_find_family_bold_returns_a_genuinely_bold_file(family):
    found = _bundled_registry.find_family(family, bold=True, italic=False)
    assert found is not None
    assert found.bold is True
    assert _macstyle(found.path, found.font_number) & 0x1


@pytestmark_bundled
@pytest.mark.parametrize("family", _STATIC_STYLED_FAMILIES)
def test_find_family_italic_returns_a_genuinely_italic_file(family):
    found = _bundled_registry.find_family(family, bold=False, italic=True)
    assert found is not None
    assert found.italic is True
    assert _macstyle(found.path, found.font_number) & 0x2


@pytestmark_bundled
def test_find_family_bold_italic_returns_true_bolditalic_when_available():
    # Tinos is the one bundled family with all four static faces.
    found = _bundled_registry.find_family("Tinos", bold=True, italic=True)
    assert found is not None
    assert found.bold is True and found.italic is True
    style = _macstyle(found.path, found.font_number)
    assert style & 0x1 and style & 0x2


@pytestmark_bundled
@pytest.mark.parametrize("family", ["Caladea", "Carlito", "Cousine"])
def test_find_family_bold_italic_prefers_italic_slant_over_bold_weight(family):
    # These families have no static BoldItalic file. Italic slant can't be faked by
    # weight-axis instancing, so the registry must hand back the Italic face (bold weight
    # is the caller's problem to fix up), not silently fall back to plain Bold or Regular.
    found = _bundled_registry.find_family(family, bold=True, italic=True)
    assert found is not None
    assert found.italic is True
    assert _macstyle(found.path, found.font_number) & 0x2


@pytestmark_bundled
@pytest.mark.parametrize("family", ["Arimo", "Noto Sans", "Noto Serif"])
def test_find_family_variable_family_bold_request_is_reported_honestly(family):
    # No static Bold file exists for these - the registry must not claim the returned
    # file is bold just because bold was requested. It honestly reports the (non-bold)
    # file it actually has; the caller instances the `wght` axis if it wants real bold.
    found = _bundled_registry.find_family(family, bold=True, italic=False)
    assert found is not None
    assert found.bold is False  # honest: this is the only file, and it isn't bold
    assert not (_macstyle(found.path, found.font_number) & 0x1)
    font = TTFont(found.path, fontNumber=found.font_number, lazy=True)
    assert "fvar" in font  # confirms it's the variable font the caller can instance


@pytestmark_bundled
def test_resolve_font_threads_bold_italic_through_substitution_table():
    # Substitution-table call site (Times New Roman -> Tinos): a bold+italic request must
    # resolve to Tinos's real BoldItalic file, not Regular.
    match = resolve_font("Times New Roman", "tr", bold=True, italic=True)
    assert match.resolved_path is not None
    style = _macstyle(match.resolved_path, match.resolved_font_number)
    assert style & 0x1 and style & 0x2


@pytestmark_bundled
def test_resolve_font_threads_bold_italic_through_bundled_name():
    # Bundled-family call site (source already names "Tinos"): same requirement.
    match = resolve_font("ABCDEF+Tinos-Regular", "tr", bold=True, italic=True)
    assert match.quality == MatchQuality.BUNDLED
    style = _macstyle(match.resolved_path, match.resolved_font_number)
    assert style & 0x1 and style & 0x2


@pytestmark_bundled
def test_resolve_font_threads_bold_through_class_fallback():
    # Class-fallback call site: "Garamond" classifies as SERIF but is in neither
    # BUNDLED_FAMILIES nor SUBSTITUTION_TABLE, so CLASS_FALLBACK["serif"] -> "Noto Serif"
    # is what gets asked for bold. Noto Serif is variable-only with no static Bold face,
    # so this must resolve honestly (not-bold macStyle) rather than fail or lie.
    match = resolve_font("Garamond", "tr", bold=True, italic=False)
    assert "classification fallback" in match.reason
    assert match.resolved_path is not None
    assert not (_macstyle(match.resolved_path, match.resolved_font_number) & 0x1)


def test_an_unrecognised_display_serif_is_answered_with_a_serif() -> None:
    """A display face is in no hint list and no substitution table, so it classifies as UNKNOWN
    and the last-resort branch used to hand every one of them a sans. The source document knows
    better: a PDF's font descriptor carries a serif flag, and `pdf_reader` now reads it into
    `Style.serif`. Seen on a real file, where a bold display serif footer came back in Arimo."""
    from layoutkeep.fitting.fontmatch import FontClass, resolve_font

    assert resolve_font("AbrilFatface-Regular", "tr").font_class is FontClass.SANS
    assert resolve_font("AbrilFatface-Regular", "tr", serif_hint=True).font_class is FontClass.SERIF
    assert resolve_font("AbrilFatface-Regular", "tr", serif_hint=False).font_class is FontClass.SANS


def test_a_family_name_we_know_outranks_the_documents_serif_flag() -> None:
    """PDF producers set that flag carelessly - the file this was found on flags Roboto, a sans,
    as serifed. The hint may only decide cases the name cannot."""
    from layoutkeep.fitting.fontmatch import FontClass, resolve_font

    assert resolve_font("Roboto-Bold", "tr", serif_hint=True).font_class is FontClass.SANS
    assert resolve_font("Times-Roman", "tr", serif_hint=False).font_class is FontClass.SERIF
