"""Builds small, reproducible raster images used by the OCR/image-reader tests.

Mirrors `build_pdf_fixture.py`: known text drawn at a known position with a known font, so the
test can check OCR output against ground truth instead of eyeballing it. Uses Pillow plus the
project's own bundled font (`assets/fonts/NotoSans-Variable.ttf`), so it needs no external files
and no network access.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = Path(__file__).parents[2] / "src" / "layoutkeep" / "assets" / "fonts" / "NotoSans-Variable.ttf"

PLAIN_TEXT = "The quick brown fox jumps over the lazy dog."
COLORED_TEXT = "Colored ground test paragraph for OCR."
IMAGE_TEXT = "Text drawn over a busy background image."
LOW_RES_TEXT = "Low resolution OCR check."
SKEW_TEXT = "Slightly skewed text line for OCR."
STRIPED_TEXT = "Text over a subtly striped paper background."
PATTERN_TEXT = "Text drawn straight onto a gradient, no plate."


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_PATH), size)


# --------------------------------------------------------------------------------------
# Ground-truth backgrounds, used by tests/test_inpaint.py to measure flat-fill adequacy:
# the exact pixel colour under the text, known because these are the same formulas the
# fixtures below paint the text on top of.
# --------------------------------------------------------------------------------------


def plain_bg_pixel(x: int, y: int) -> tuple[int, int, int]:
    return (255, 255, 255)


def colored_bg_pixel(x: int, y: int) -> tuple[int, int, int]:
    return (30, 60, 120)


def striped_bg_pixel(x: int, y: int) -> tuple[int, int, int]:
    return (235, 235, 235) if (x // 10) % 2 == 0 else (215, 215, 215)


def pattern_bg_pixel(x: int, y: int) -> tuple[int, int, int]:
    return (x % 256, (y * 2) % 256, (x + y) % 256)


def text_bbox(text: str, font_size: int, origin: tuple[int, int]) -> tuple[int, int, int, int]:
    """Exact glyph bbox for `text` drawn with `_font(font_size)` at `origin`, used as ground
    truth by the inpaint measurement instead of relying on OCR's own (imperfect) box."""
    scratch = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(scratch)
    x0, y0, x1, y1 = draw.textbbox(origin, text, font=_font(font_size))
    return (x0, y0, x1, y1)


def build_plain_white(path: str | Path) -> None:
    """Plain white ground, black text - the easy case."""
    img = Image.new("RGB", (600, 150), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 60), PLAIN_TEXT, font=_font(24), fill="black")
    img.save(path)


def build_colored_ground(path: str | Path) -> None:
    """Solid coloured background with contrasting text colour, to exercise colour detection."""
    img = Image.new("RGB", (600, 150), (30, 60, 120))  # dark blue
    d = ImageDraw.Draw(img)
    d.text((30, 60), COLORED_TEXT, font=_font(24), fill=(255, 220, 0))  # yellow
    img.save(path)


def build_text_over_image(path: str | Path) -> None:
    """Text over a photo-like background: a gradient plus noise-ish stripes, not a flat fill."""
    img = Image.new("RGB", (600, 150))
    px = img.load()
    for x in range(img.width):
        for y in range(img.height):
            px[x, y] = (x % 256, (y * 2) % 256, (x + y) % 256)
    d = ImageDraw.Draw(img)
    # A solid plate behind the text keeps it legible while the rest of the image stays busy,
    # matching the "text over an image" fixture description without needing OCR to read text
    # painted directly over high-frequency noise.
    d.rectangle((20, 50, 580, 100), fill=(0, 0, 0))
    d.text((30, 60), IMAGE_TEXT, font=_font(22), fill="white")
    img.save(path)


def build_low_resolution(path: str | Path) -> None:
    """Same text as the plain case, rendered small and then scaled down to blur it."""
    img = Image.new("RGB", (500, 150), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 60), LOW_RES_TEXT, font=_font(24), fill="black")
    img = img.resize((150, 45), Image.BILINEAR).resize((500, 150), Image.BILINEAR)
    img.save(path)


def build_striped_ground(path: str | Path) -> None:
    """Faint, low-contrast paper-like stripes - the "flat-ish" background common in real scans."""
    img = Image.new("RGB", (600, 150))
    px = img.load()
    for x in range(img.width):
        for y in range(img.height):
            px[x, y] = striped_bg_pixel(x, y)
    d = ImageDraw.Draw(img)
    d.text((30, 60), STRIPED_TEXT, font=_font(22), fill="black")
    img.save(path)


def build_text_over_pattern(path: str | Path) -> None:
    """Text drawn straight onto a high-frequency gradient, no solid plate behind it - the case
    the cheap flat-fill inpaint is expected to fail on."""
    img = Image.new("RGB", (600, 150))
    px = img.load()
    for x in range(img.width):
        for y in range(img.height):
            px[x, y] = pattern_bg_pixel(x, y)
    d = ImageDraw.Draw(img)
    d.text((30, 60), PATTERN_TEXT, font=_font(22), fill="white")
    img.save(path)


def build_skewed(path: str | Path) -> None:
    """Same text, rotated a few degrees to simulate a crooked scan."""
    img = Image.new("RGB", (600, 220), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 60), SKEW_TEXT, font=_font(24), fill="black")
    img = img.rotate(4, resample=Image.BICUBIC, expand=True, fillcolor="white")
    img.save(path)


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    build_plain_white(out_dir / "img_plain_white.png")
    build_colored_ground(out_dir / "img_colored_ground.png")
    build_text_over_image(out_dir / "img_text_over_image.png")
    build_low_resolution(out_dir / "img_low_resolution.png")
    build_skewed(out_dir / "img_skewed.png")
