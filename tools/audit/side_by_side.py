"""Put the original page and one or more translated versions of it side by side, one image a page.

Metrics were never the judge on this project; looking at the output next to the source was, and
it found every defect the numbers missed. This makes that comparison cheap to repeat and keeps
the images, instead of relying on memory of what a run looked like.

    python tools/audit/side_by_side.py SOURCE.pdf off=OUT_A.pdf on=OUT_B.pdf --out DIR
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


def _render(doc: pymupdf.Document, index: int, dpi: int) -> Image.Image:
    pix = doc[index].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("outputs", nargs="+", help="label=path.pdf")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=110)
    parser.add_argument("--names", default="", help="comma-separated page names for file names")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    labelled = [(item.split("=", 1)[0], pymupdf.open(item.split("=", 1)[1])) for item in args.outputs]
    names = args.names.split(",") if args.names else []
    with pymupdf.open(str(args.source)) as source:
        for index in range(source.page_count):
            panels = [("original", _render(source, index, args.dpi))]
            panels += [(label, _render(doc, index, args.dpi)) for label, doc in labelled]
            gap, band = 12, 26
            width = sum(p.width for _, p in panels) + gap * (len(panels) - 1)
            height = max(p.height for _, p in panels) + band
            sheet = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(sheet)
            x = 0
            for label, panel in panels:
                draw.text((x + 6, 6), label, fill="black")
                sheet.paste(panel, (x, band))
                draw.rectangle((x, band, x + panel.width - 1, band + panel.height - 1), outline="gray")
                x += panel.width + gap
            name = names[index] if index < len(names) else f"{index + 1:03d}"
            sheet.save(args.out / f"page_{name}.jpg", quality=85)
            print(args.out / f"page_{name}.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
