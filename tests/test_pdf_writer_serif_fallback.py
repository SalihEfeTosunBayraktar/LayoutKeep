"""A serif source is not drawn in a sans when no font file could be resolved for it.

The writer's last resort mapped a font to a generic family by its name alone, so every serif
whose name gives no hint - URW Palladio (Think Python), Nimbus Roman (arXiv, pdfLaTeX), Computer
Modern - became Helvetica. The PDF says whether a face is serifed; the fallback now asks it when
the name cannot answer, and a name it recognises still wins, as in font resolution.
"""

from __future__ import annotations

from layoutkeep.core.docir import Style
from layoutkeep.writers.pdf_writer import _FontResolver


def test_an_unresolved_serif_falls_back_to_a_serif() -> None:
    resolver = _FontResolver("tr")
    assert resolver.css_family_for(Style(font_family="URWPalladioL-Roma", serif=True)) == "serif"
    assert resolver.css_family_for(Style(font_family="NimbusRomNo9L-ReguItal", serif=True, italic=True)) == "serif"


def test_a_recognised_sans_name_outranks_a_careless_serif_flag() -> None:
    resolver = _FontResolver("tr")
    assert resolver.css_family_for(Style(font_family="Roboto-Regular", serif=True)) == "sans-serif"
    assert resolver.css_family_for(Style(font_family="SFTT1000", serif=False)) == "sans-serif"
