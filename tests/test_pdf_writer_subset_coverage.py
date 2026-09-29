"""An embedded subset is reused only if it holds every character the translation draws.

Turkish Penal Code, translated to English: the source embeds a Times New Roman subset cut to the
letters Turkish uses - no w, q or x. The coverage check only asked for the target language's
letters outside ASCII, and English has none, so the subset was declared complete and reused: every
w, q and x of the translation ("Who", "eXisting", "freQuented", "tWo") was drawn from another face.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from fontTools import subset

from layoutkeep.core.docir import Style
from layoutkeep.fitting.fontmatch import MatchQuality, _bundled_font_dir
from layoutkeep.writers.pdf_writer import _FontResolver

_TURKISH = "Kara, deniz, hava veya demiryolu ulaşımında kişilerin hayatı"


def _page_with_a_turkish_subset(tmp_path: Path) -> pymupdf.Page:
    options = subset.Options()
    options.name_IDs = ["*"]
    font = subset.load_font(str(Path(_bundled_font_dir()) / "Caladea-Regular.ttf"), options)
    cutter = subset.Subsetter(options)
    cutter.populate(text=_TURKISH)
    cutter.subset(font)
    buffer = io.BytesIO()
    font.save(buffer)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="Caladea", fontbuffer=buffer.getvalue())
    page.insert_text((72, 100), _TURKISH, fontname="Caladea", fontsize=11)
    path = tmp_path / "turkish.pdf"
    doc.save(path)
    return pymupdf.open(path)[0]


def test_a_subset_missing_a_letter_of_the_translation_is_not_reused(tmp_path: Path) -> None:
    page = _page_with_a_turkish_subset(tmp_path)
    family = page.get_fonts()[0][3].split("+")[-1]
    style = Style(font_family=family, size=11.0, serif=True)
    resolver = _FontResolver("en")

    resolver._register_style(page, style, "A person who fails to place the required signs")
    resolver.finalize()

    match = next(iter(resolver._matches.values()))
    assert match.quality is not MatchQuality.ORIGINAL, match.reason


def test_a_subset_that_holds_every_letter_is_still_reused(tmp_path: Path) -> None:
    page = _page_with_a_turkish_subset(tmp_path)
    family = page.get_fonts()[0][3].split("+")[-1]
    style = Style(font_family=family, size=11.0, serif=True)
    resolver = _FontResolver("en")

    resolver._register_style(page, style, "deniz hava")
    resolver.finalize()

    match = next(iter(resolver._matches.values()))
    assert match.quality is MatchQuality.ORIGINAL, match.reason
