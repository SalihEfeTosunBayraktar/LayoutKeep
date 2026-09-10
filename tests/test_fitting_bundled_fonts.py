"""Integrity of the bundled substitute fonts (`assets/fonts/`, see its README).

These fonts exist specifically because most machines lack metric-compatible, glyph-complete
substitutes for Times New Roman/Arial/etc. If a bundled file goes missing, or gets replaced by
one that lost Turkish/German/Polish coverage, `fontmatch.resolve_font()` would silently degrade
to a worse font or fail to render - the whole point of bundling is that this must never be
silent. These tests make it loud instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from layoutkeep.fitting.fontmatch import (
    REQUIRED_GLYPHS,
    FontRegistry,
    MatchQuality,
    _bundled_font_dir,
    missing_glyphs,
    resolve_font,
)

# Every file the README promises is bundled.
EXPECTED_BUNDLED_FILES = [
    "Tinos-Regular.ttf",
    "Tinos-Bold.ttf",
    "Tinos-Italic.ttf",
    "Tinos-BoldItalic.ttf",
    "Arimo-Variable.ttf",
    "Arimo-Italic-Variable.ttf",
    "Cousine-Regular.ttf",
    "Cousine-Bold.ttf",
    "Cousine-Italic.ttf",
    "Cousine-BoldItalic.ttf",
    "Caladea-Regular.ttf",
    "Caladea-Bold.ttf",
    "Caladea-Italic.ttf",
    "Caladea-BoldItalic.ttf",
    "Carlito-Regular.ttf",
    "Carlito-Bold.ttf",
    "Carlito-Italic.ttf",
    "Carlito-BoldItalic.ttf",
    "NotoSans-Variable.ttf",
    "NotoSerif-Variable.ttf",
]


def test_bundled_font_dir_is_found():
    bundled = _bundled_font_dir()
    assert bundled is not None, "assets/fonts could not be located - see fontmatch._bundled_font_dir()"
    assert Path(bundled).is_dir()


def test_all_expected_bundled_files_present():
    bundled = _bundled_font_dir()
    assert bundled is not None
    present = {p.name for p in Path(bundled).glob("*.ttf")}
    missing_files = [f for f in EXPECTED_BUNDLED_FILES if f not in present]
    assert not missing_files, f"bundled fonts missing from {bundled}: {missing_files}"


@pytest.mark.parametrize("filename", EXPECTED_BUNDLED_FILES)
@pytest.mark.parametrize("lang", sorted(REQUIRED_GLYPHS))
def test_bundled_font_covers_required_glyphs(filename, lang):
    bundled = _bundled_font_dir()
    assert bundled is not None
    path = Path(bundled) / filename
    assert path.is_file(), f"{filename} is listed as bundled but is missing on disk"
    missing = missing_glyphs(str(path), REQUIRED_GLYPHS[lang])
    assert missing == "", f"{filename} lost {lang!r} glyph coverage: missing {missing!r}"


def test_default_registry_prefers_bundled_tinos_over_system_fonts():
    reg = FontRegistry()  # default dirs: bundled first, then system
    bundled = _bundled_font_dir()
    found = reg.find_family("Tinos")
    assert bundled is not None
    assert found is not None
    assert found.path.startswith(bundled)


def test_resolve_font_reports_bundled_substitute_by_default():
    match = resolve_font("Times New Roman", "tr")
    assert match.resolved_path is not None
    assert match.quality is MatchQuality.SUBSTITUTE
    assert "bundled" in match.reason.lower()
