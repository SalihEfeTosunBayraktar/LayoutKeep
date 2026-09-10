"""Image writer: draws a translated DocIR Document back onto its source raster image(s).

Strategy (see docs/CONTRACT.md and the phase-2 brief): for every translatable block, the box is
cleared with `ocr.inpaint.inpaint_block` and the block's current text (the translation once the
pipeline has applied it, or the original OCR text if it has not been translated yet) is drawn
back in with a font resolved through `fitting/fontmatch.py`. Sizing/line-breaking is NOT decided
here - `fitting/fit.py`'s `fit_segment` plus `fitting/measure.py`'s fontTools-based
`TextMeasurer` (the same PyMuPDF-free measurement seam the PDF writer's own fitting call goes
through, see CONTRACT.md D3) is called to get the final text and scale; this module only applies
that result.

A page whose source document was a scanned PDF (`Document.source_format == "pdf"`) is written
back as a PDF, not a bare image file, via Pillow's own PDF writer - this module must not
`import pymupdf` (CONTRACT.md S4 reserves that to the two PDF modules).
"""

from __future__ import annotations

import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from layoutkeep.core.docir import Block, Document, Page, Segment, Style
from layoutkeep.fitting import FitMode, TextMeasurer, fit_segment, make_measure_fn, resolve_font
from layoutkeep.ocr.inpaint import inpaint_block


def write_image(doc: Document, source_path: str | Path, out_path: str | Path) -> None:
    """Render `doc` (read from `source_path`, possibly with translations applied) to `out_path`."""
    rendered = [_render_page(page, doc.target_lang, fallback_source=source_path) for page in doc.pages]

    out_path = Path(out_path)
    if doc.source_format == "pdf":
        first, *rest = rendered
        first.save(out_path, format="PDF", save_all=True, append_images=rest)
    else:
        rendered[0].save(out_path)


def _render_page(page: Page, target_lang: str | None, *, fallback_source: str | Path) -> Image.Image:
    src = Path(page.source_ref) if page.source_ref else Path(fallback_source)
    image = Image.open(src).convert("RGB")
    for block in page.blocks_in_reading_order():
        if not block.translatable:
            continue
        image = inpaint_block(image, block)
        _draw_block(image, block, target_lang)
    return image


def _draw_block(image: Image.Image, block: Block, target_lang: str | None) -> None:
    text = block.text
    if not text.strip():
        return
    style = block.dominant_style()
    font_path = _resolve_font_path(style, target_lang)

    # `Style.size` on an image-read block is in points (see readers/image_reader.py), but
    # `Block.bbox` is in this image's own pixel space, so the two units must not be mixed when
    # measuring/drawing. A copy of the style with size in pixels (the block's own measured line
    # height) keeps `fit_segment`/`TextMeasurer` consistent with the pixel bbox without touching
    # the reader's tested point-size formula.
    px_style = _style_in_pixels(style, block)

    measurer = TextMeasurer(font_path)
    measure = make_measure_fn(measurer)
    segment = Segment(block_id=block.id, source=text, target=text)
    result = fit_segment(segment, px_style, block.bbox, measure, mode=FitMode.STRICT)
    if result.needs_review:
        block.needs_review = True

    final_size = px_style.size * result.scale
    lines = measurer.wrap_lines(result.text, final_size, block.bbox.width)
    pil_font = ImageFont.truetype(font_path, max(1, round(final_size)))

    draw = ImageDraw.Draw(image)
    line_height = style.line_height if style.line_height is not None else final_size * 1.2
    y = block.bbox.y0
    for line in lines:
        draw.text((block.bbox.x0, y), line, font=pil_font, fill=_hex_to_rgb(style.color))
        y += line_height


def _style_in_pixels(style: Style, block: Block) -> Style:
    """Copy of `style` with `size` expressed in the block's own pixel space (see `_draw_block`)."""
    heights = [line.bbox.height for line in block.lines if line.bbox is not None]
    px_size = statistics.median(heights) if heights else block.bbox.height
    return Style(
        font_family=style.font_family,
        size=px_size,
        bold=style.bold,
        italic=style.italic,
        color=style.color,
        background=style.background,
        letter_spacing=style.letter_spacing,
        line_height=style.line_height,
        font_path=style.font_path,
    )


def _resolve_font_path(style: Style, target_lang: str | None) -> str:
    if style.font_path:
        return style.font_path
    match = resolve_font(
        style.font_family or "sans-serif",
        target_lang or "",
        bold=style.bold,
        italic=style.italic,
        serif_hint=style.serif,
    )
    if not match.resolved_path:
        raise RuntimeError(
            f"font resolution failed for family={style.font_family!r}: {match.reason}"
        )
    return match.resolved_path


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
