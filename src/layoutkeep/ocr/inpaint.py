"""Text removal for scanned images: clear a detected text box so the writer can draw the
translated line in its place.

Cheap path only (see docs/CONTRACT.md and the phase-2 brief): fill the box with the background
colour `readers/image_reader.py` already found via its 2-means colour split. No inpainting model
is used - LaMa's weights are CC BY-NC-SA and cannot ship inside this AGPL-3.0-or-later project
(same reasoning `ocr/engine.py` applies to ruling out Surya's RAIL-M weights for OCR). Whether
the flat fill is visually adequate is a measured question, not an assumption - see
`tests/test_inpaint.py` for the numbers on the project's fixtures.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from layoutkeep.core.docir import BBox, Block


def flat_fill(image: Image.Image, bbox: BBox, color: str) -> Image.Image:
    """Return a copy of `image` with `bbox` painted solid `color` (an "#rrggbb" hex string).

    This is the whole cheap-path primitive: no model, just paint over the box with a colour
    already measured from the image. Adequate when the ground under the text is locally uniform.
    """
    out = image.copy()
    ImageDraw.Draw(out).rectangle((bbox.x0, bbox.y0, bbox.x1, bbox.y1), fill=_hex_to_rgb(color))
    return out


def inpaint_block(image: Image.Image, block: Block) -> Image.Image:
    """Clear every span in `block` with that span's own detected background colour.

    Filling per span (rather than the whole block bbox at once) matters when a block mixes
    colours, e.g. a highlighted word inside an otherwise plain-background paragraph.
    """
    out = image.copy()
    draw = ImageDraw.Draw(out)
    fallback = block.dominant_style().background or "#ffffff"
    for line in block.lines:
        for span in line.spans:
            color = span.style.background or fallback
            draw.rectangle(
                (span.bbox.x0, span.bbox.y0, span.bbox.x1, span.bbox.y1), fill=_hex_to_rgb(color)
            )
    return out


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
