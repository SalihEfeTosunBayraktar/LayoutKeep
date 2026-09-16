"""Scanned pages in deliberately different styles, one per assumption the reader makes.

Every constant in the scanned-page path was calibrated on `computer-systems-Architecture.pdf`
and several later broke a different page of the same book. A second real document
(`Notes_260730_153127.pdf`, A4 at ~100 DPI) then broke the page-is-scanned test outright. The
accepted discipline in the field is to hold out document *types* rather than more pages of the
same document - DocLayNet and M6Doc are built that way - and this machine has no third real
scan, so the styles are built.

Each style varies exactly one thing the reader assumes, so a regression says which assumption
broke:

    small_trim      the reference: the textbook's shape - 318x424pt, tight leading,
                    first-line indents, one column, margin keywords
    a4_loose        A4 with generous leading and NO indent - paragraphs separated by a blank
                    line instead, which is the only other way prose is set
    two_column      two columns, which the reader has no column detection for at all
    ragged_right    unjustified text, so line lengths vary and the "long line" test for the
                    body column has a noisier population to work from
    large_print     type at twice the size, so anything expressed in absolute points rather
                    than relative to the page is exposed
    turkish         Turkish text with diacritics, so the letters-per-character test that
                    decides what is prose and what is a grid has non-ASCII to chew on

Each is rendered to an image and embedded as a full-page picture, so the reader sees a scan and
not a text layer. `--dpi` controls the render, because resolution is itself one of the
assumptions: the book is 600 DPI and the notes document is ~100.

    python tests/fixtures/build_scanned_styles.py --out _artifacts/styles --dpi 200
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

#: Page sizes in points. A small trim like the textbook's, and A4.
SMALL_TRIM = (318.0, 424.0)
A4 = (596.0, 842.0)

BODY_EN = (
    "The enable input may be activated with a zero or with a one signal level. Some decoders "
    "have two or more enable inputs that must satisfy a given logic condition in order to "
    "enable the circuit. There are occasions when a certain-size decoder is needed but only "
    "smaller sizes are available."
)
BODY_TR = (
    "Etkinlestirme girisi sifir veya bir sinyal seviyesiyle etkinlestirilebilir. Bazi "
    "cozuculer, devreyi etkinlestirmek icin belirli bir mantik kosulunu saglamasi gereken iki "
    "veya daha fazla etkinlestirme girisine sahiptir. Cogu zaman belirli bir boyutta cozucu "
    "gerekir ancak yalnizca daha kucuk boyutlar bulunur."
)
BODY_TR_DIACRITIC = (
    "Etkinleştirme girişi sıfır veya bir sinyal seviyesiyle etkinleştirilebilir. Bazı "
    "çözücüler, devreyi etkinleştirmek için belirli bir mantık koşulunu sağlaması gereken iki "
    "veya daha fazla etkinleştirme girişine sahiptir. Çoğu zaman belirli bir boyutta çözücü "
    "gerekir ancak yalnızca daha küçük boyutlar bulunur."
)
MARGIN_WORDS = ("decoder", "enable", "inverter")


def _font(pixels: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, pixels)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    lines: list[str] = []
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_paragraphs(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font,
    left: float,
    top: float,
    width: float,
    pitch: float,
    indent: float,
    blank_between: bool,
    paragraphs: int,
    margin_words: bool,
    scale: float,
) -> float:
    """Lay out `paragraphs` copies of `text` and return the y it finished at."""
    y = top
    for index in range(paragraphs):
        lines = _wrap(draw, text, font, width - (indent if index or indent else 0))
        for line_index, line in enumerate(lines):
            x = left + (indent if line_index == 0 else 0.0)
            draw.text((x, y), line, fill="black", font=font)
            if margin_words and line_index == 0 and index < len(MARGIN_WORDS):
                # A keyword in the left margin, level with the paragraph it introduces.
                draw.text((12 * scale, y), MARGIN_WORDS[index], fill="black", font=font)
            y += pitch
        if blank_between:
            y += pitch
    return y


def _page_image(
    size_pt: tuple[float, float],
    dpi: float,
    painter,
) -> Image.Image:
    scale = dpi / 72.0
    image = Image.new("RGB", (int(size_pt[0] * scale), int(size_pt[1] * scale)), "white")
    painter(ImageDraw.Draw(image), scale)
    return image


def _embed(image: Image.Image, size_pt: tuple[float, float], out: Path) -> None:
    """Write the image as the whole content of one PDF page - a scan, not a text layer."""
    png = out.with_suffix(".png")
    image.save(png)
    doc = pymupdf.open()
    page = doc.new_page(width=size_pt[0], height=size_pt[1])
    page.insert_image(pymupdf.Rect(0, 0, *size_pt), filename=str(png))
    doc.save(str(out))
    doc.close()
    png.unlink()


def _style_small_trim(draw: ImageDraw.ImageDraw, scale: float) -> None:
    font = _font(int(6.5 * scale))
    draw.text((10 * scale, 12 * scale), "46 CHAPTER TWO Digital Components", fill="black", font=font)
    _draw_paragraphs(
        draw, text=BODY_EN, font=font, left=74 * scale, top=32 * scale,
        width=233 * scale, pitch=7.9 * scale, indent=16.6 * scale,
        blank_between=False, paragraphs=3, margin_words=True, scale=scale,
    )


def _style_a4_loose(draw: ImageDraw.ImageDraw, scale: float) -> None:
    """No indent at all: paragraphs separated by a blank line, generous leading."""
    font = _font(int(11 * scale))
    _draw_paragraphs(
        draw, text=BODY_EN, font=font, left=70 * scale, top=70 * scale,
        width=456 * scale, pitch=16.0 * scale, indent=0.0,
        blank_between=True, paragraphs=3, margin_words=False, scale=scale,
    )


def _style_two_column(draw: ImageDraw.ImageDraw, scale: float) -> None:
    font = _font(int(9 * scale))
    for column in (0, 1):
        left = (60 + column * 250) * scale
        _draw_paragraphs(
            draw, text=BODY_EN, font=font, left=left, top=70 * scale,
            width=210 * scale, pitch=12.0 * scale, indent=12.0 * scale,
            blank_between=False, paragraphs=2, margin_words=False, scale=scale,
        )


def _style_ragged_right(draw: ImageDraw.ImageDraw, scale: float) -> None:
    """Unjustified, and deliberately varied line lengths."""
    font = _font(int(10 * scale))
    y = 70 * scale
    for index, sentence in enumerate(BODY_EN.split(". ")):
        draw.text(((70 + (index % 3) * 4) * scale, y), sentence.strip(), fill="black", font=font)
        y += 15.0 * scale


def _style_large_print(draw: ImageDraw.ImageDraw, scale: float) -> None:
    font = _font(int(22 * scale))
    _draw_paragraphs(
        draw, text=BODY_EN, font=font, left=60 * scale, top=70 * scale,
        width=470 * scale, pitch=30.0 * scale, indent=30.0 * scale,
        blank_between=False, paragraphs=2, margin_words=False, scale=scale,
    )


def _style_turkish(draw: ImageDraw.ImageDraw, scale: float) -> None:
    font = _font(int(10 * scale))
    _draw_paragraphs(
        draw, text=BODY_TR_DIACRITIC, font=font, left=70 * scale, top=70 * scale,
        width=456 * scale, pitch=14.0 * scale, indent=14.0 * scale,
        blank_between=False, paragraphs=3, margin_words=False, scale=scale,
    )


STYLES: dict[str, tuple[tuple[float, float], object]] = {
    "small_trim": (SMALL_TRIM, _style_small_trim),
    "a4_loose": (A4, _style_a4_loose),
    "two_column": (A4, _style_two_column),
    "ragged_right": (A4, _style_ragged_right),
    "large_print": (A4, _style_large_print),
    "turkish": (A4, _style_turkish),
}


def build(out_dir: Path, dpi: float) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, (size_pt, painter) in STYLES.items():
        path = out_dir / f"{name}_{int(dpi)}dpi.pdf"
        _embed(_page_image(size_pt, dpi, painter), size_pt, path)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("_artifacts/styles"))
    parser.add_argument(
        "--dpi", type=float, action="append",
        help="render resolution; repeatable. Defaults to 100, 200 and 600 - the range the two "
             "real documents span.",
    )
    args = parser.parse_args()
    for dpi in args.dpi or [100.0, 200.0, 600.0]:
        for path in build(args.out, dpi):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
