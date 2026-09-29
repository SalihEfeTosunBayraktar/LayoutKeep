"""Telling an equation block from prose by its fonts and characters.

Denklem bloğunu yazı tipi ve karakterlerinden düzyazıdan ayırt eder.
"""

from __future__ import annotations

from layoutkeep.core.docir import (
    Line,
)

#: Fonts that only ever typeset mathematics. A block set in one of these is a formula, not
#: prose, and must not be sent to a translator (BlockRole.FORMULA is non-translatable).
#: CMR10 is deliberately absent: LaTeX sets *body text* in Computer Modern Roman too, so a
#: CMR10-only block is ordinary prose, not math. The faces below are the ones LaTeX uses for
#: the symbols and variables *inside* equations (CM math italic/symbol/extension, AMS) and
#: modern OpenType math fonts.
_MATH_FONT_MARKERS = (
    "CMEX",   # Computer Modern math extension (big operators, delimiters)
    "CMSY",   # Computer Modern math symbols
    "CMMI",   # Computer Modern math italic (variables: x, y, \alpha)
    "MSAM",   # AMS symbols A
    "MSBM",   # AMS symbols B
    "Euler",  # AMS Euler math
    "rsfs",   # Ralph Smith formal script (math)
    "math",   # any font with "math" in its name (STIX Math, XITS Math, Latin Modern Math)
)

#: Lowercased once at import; the block check compares against lowercased font names so a
#: subset-prefixed or case-shifted report ("ABCDEF+CMMI10", "cmmi10") still matches.
_MATH_FONT_MARKERS_LOWER = tuple(m.lower() for m in _MATH_FONT_MARKERS)

#: Common body-text faces. A paragraph that happens to contain an inline symbol set in a math
#: face (LaTeX sets \dag, \times, variables inline in CMSY/CMMI) must stay BODY and be
#: translated - only a block with NO prose face at all is a pure displayed equation.
#:
#: CMR10 (Computer Modern Roman) is intentionally NOT here: it is ambiguous. Ghostscript-built
#: PDFs (this repo's academic corpus) substitute the prose body with Nimbus/Times and keep
#: CMR10 only for the roman fragments *inside* equations ("= softmax"), so treating CMR10 as
#: prose would freeze those equations as BODY. Raw dvips PDFs instead set the whole body in
#: CMR10 - treating it as math would freeze every paragraph. The disambiguator below is
#: therefore structural, not font-based: a CMR10 block is an equation only when it is short
#: (a displayed equation fits in a couple of lines), and prose otherwise.
_PROSE_FONT_MARKERS = (
    "nimbus", "times", "dejavu", "helvetica", "arial", "dmsans", "calibri",
    "tinos", "arimo", "cousine", "caladea", "liberation", "noto", "roboto",
    "georgia", "verdana", "cambria", "garamond", "palatino",
)

#: Displayed equations built by TeX sit on their own, one to a few lines. A CMR10-bearing
#: block longer than this is body prose (LaTeX paragraph), not an equation.
_MAX_EQUATION_CHARS = 200


def _looks_like_math(lines: list[Line]) -> bool:
    """True when a block is a displayed equation, not readable prose.

    Academic PDFs (LaTeX) render each displayed equation as its own text block. The block's
    faces are the math fonts (CMMI/CMSY/CMEX, AMS MSAM/MSBM) - never a prose face - and the
    glyphs often map to low/private-use code points (\\x10, \\uf8ee) that no model could
    translate. Sending them to a translator corrupts them; they are layout the reader must
    carry through untouched, exactly what BlockRole.FORMULA exists for.

    The check is deliberately conservative in both directions:
    - A prose face anywhere in the block (Nimbus/Times/DejaVu/...) keeps it BODY even when
      inline symbols use a math face - "We show x \\in R ..." is a sentence with inline
      math, not an equation, and must still be translated.
    - CMR10 alone is NOT math (LaTeX body prose is set in it), and a CMR10-bearing block is
      only classified as an equation when it is short enough to be one; a long multi-line
      CMR10 block is a paragraph.
    """
    has_math = False
    has_prose = False
    has_cmr10 = False
    total_chars = 0
    for line in lines:
        for span in line.spans:
            text = span.text or ""
            total_chars += len(text)
            font = (span.style.font_family or "").lower()
            if any(marker in font for marker in _MATH_FONT_MARKERS_LOWER):
                has_math = True
            if any(marker in font for marker in _PROSE_FONT_MARKERS):
                has_prose = True
            if "cmr" in font:
                has_cmr10 = True
    if not has_math or has_prose:
        return False
    # Pure math faces (no CMR10 at all): unambiguous equation.
    if not has_cmr10:
        return True
    # CMR10-bearing: equation only when short - a long block is a LaTeX paragraph whose
    # inline math spans happened to be the ones that matched.
    return total_chars <= _MAX_EQUATION_CHARS
