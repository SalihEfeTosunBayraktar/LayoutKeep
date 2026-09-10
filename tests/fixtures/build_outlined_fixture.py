"""Builds rendered-page fixtures for `tests/test_outlined_text.py`.

`ocr.outlined_text.find_outlined_text` never touches a real PDF - it takes a rendered page image
plus whatever string the caller says is the text layer (`Page.get_text()` in production). So a
fixture only needs to draw text at known positions with Pillow; there is no need to fabricate an
actual PDF with vector-outline glyphs to exercise the detection logic, since drawn/outlined text
and font-set text are visually identical - the only difference is whether it shows up in the
string passed alongside the image, which these builders control directly.

Mirrors `build_image_fixture.py`'s approach (known text at known position, no external files).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = Path(__file__).parents[2] / "src" / "layoutkeep" / "assets" / "fonts" / "NotoSans-Variable.ttf"

# What the fake text layer reports for the mixed fixture - everything except OUTLINED, mirroring
# the real-world case: a logo word converted to curves sits next to ordinary body text.
BODY_TEXT = "This is normal body text drawn as a real font run."
OUTLINED_WORD = "OUTLINED"
FULLY_COVERED_TEXT = "Every word on this page is present in the text layer."


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_PATH), size)


def build_mixed_page(path: str | Path) -> None:
    """A page with ordinary text plus one word that the text layer will not report."""
    img = Image.new("RGB", (700, 220), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 40), BODY_TEXT, font=_font(20), fill="black")
    d.text((30, 130), OUTLINED_WORD, font=_font(28), fill="black")
    img.save(path)


def build_fully_covered_page(path: str | Path) -> None:
    """A page whose every visible word is also in the text layer - false-positive check."""
    img = Image.new("RGB", (700, 150), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 60), FULLY_COVERED_TEXT, font=_font(20), fill="black")
    img.save(path)


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    build_mixed_page(out_dir / "outlined_mixed_page.png")
    build_fully_covered_page(out_dir / "outlined_fully_covered_page.png")
