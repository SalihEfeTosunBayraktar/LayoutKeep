"""Compose a before/after image from a source document and its translation.

The claim the project makes is about layout, and a claim about layout has to be shown rather
than described. This renders the first page of each file at the same scale, puts them side by
side with a label over each, and writes one PNG.

    .venv/Scripts/python.exe tools/make_comparison_image.py source.pdf translated.pdf out.png \
        --left "Source (EN)" --right "Translation (TR)"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

#: Rendered at this DPI, then labelled. High enough that the two-column text is legible in a
#: README at half width.
DPI = 120

LABEL_HEIGHT = 46
GAP = 18
MARGIN = 18
BACKGROUND = (248, 250, 252)
LABEL_COLOR = (15, 23, 42)
BORDER = (203, 213, 225)


def _render(path: Path) -> Image.Image:
    document = pymupdf.open(str(path))
    pixmap = document[0].get_pixmap(dpi=DPI)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    document.close()
    return image


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose(left_pdf: Path, right_pdf: Path, out: Path, left_text: str, right_text: str) -> Path:
    left, right = _render(left_pdf), _render(right_pdf)
    height = max(left.height, right.height)
    width = MARGIN * 2 + left.width + GAP + right.width

    canvas = Image.new("RGB", (width, height + LABEL_HEIGHT + MARGIN * 2), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    font = _font(22)

    for image, text, x in (
        (left, left_text, MARGIN),
        (right, right_text, MARGIN + left.width + GAP),
    ):
        draw.text((x + 2, MARGIN + 8), text, fill=LABEL_COLOR, font=font)
        top = MARGIN + LABEL_HEIGHT
        canvas.paste(image, (x, top))
        draw.rectangle(
            [x - 1, top - 1, x + image.width, top + image.height], outline=BORDER, width=1
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out), optimize=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("translated")
    parser.add_argument("out")
    parser.add_argument("--left", default="Source")
    parser.add_argument("--right", default="Translation")
    args = parser.parse_args()

    written = compose(
        Path(args.source), Path(args.translated), Path(args.out), args.left, args.right
    )
    print(f"{written} yazildi ({written.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
