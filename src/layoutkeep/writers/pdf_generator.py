"""PDF generator: creates a new PDF from a DocIR Document for cross-format export.

DocIR dokümanından sıfırdan PDF üreten çapraz format dışa aktarım modülü.
"""

from __future__ import annotations

import base64
import contextlib
import html
from pathlib import Path

import pymupdf

from layoutkeep.core.docir import Block, BlockRole, Document, ImageRef, Page, Span

_A4_WIDTH = 595.0
_A4_HEIGHT = 842.0
_MARGIN = 48.0
_EPUB_PDF_PAGE_SIZE = "a4"

#: Points of white space on every side of the text. 56pt is about 2cm, the low end of what a
#: printed page uses and enough that nothing sits against the edge.
_PAGE_MARGIN = 56.0


def _span_to_html(span: Span) -> str:
    # Metin parçasını stilini koruyarak HTML'e çevirir / Renders styled span for PDF
    txt = html.escape(span.text)
    if not txt:
        return ""
    if span.style.bold:
        txt = f"<b>{txt}</b>"
    if span.style.italic:
        txt = f"<i>{txt}</i>"
    styles: list[str] = []
    if span.style.color and span.style.color != "#000000":
        styles.append(f"color: {span.style.color}")
    if span.style.size > 0:
        styles.append(f"font-size: {span.style.size:.1f}pt")
    if styles:
        txt = f'<span style="{"; ".join(styles)}">{txt}</span>'
    return txt


def _block_html(block: Block) -> str:
    # Blok metnini stilleri koruyarak HTML formatına çevirir / Converts block to styled HTML
    lines_html: list[str] = []
    for line in block.lines:
        line_str = "".join(_span_to_html(span) for span in line.spans)
        if line_str:
            lines_html.append(line_str)

    content = "<br/>".join(lines_html) if lines_html else html.escape(block.text.strip()).replace("\n", "<br/>")
    if not content.strip():
        return ""
    align_style = f"text-align: {block.align}; " if block.align and block.align != "left" else ""
    if block.role == BlockRole.TITLE:
        return f"<h1 style='font-size: 18pt; margin-bottom: 8pt; color: #1e293b; {align_style}'>{content}</h1>"
    if block.role == BlockRole.HEADING:
        return f"<h2 style='font-size: 13pt; margin-top: 10pt; margin-bottom: 6pt; color: #334155; {align_style}'>{content}</h2>"
    if block.role == BlockRole.CODE:
        return f"<pre style='font-size: 8.5pt; background: #f1f5f9; padding: 4pt; border-radius: 4px;'>{content}</pre>"
    return f"<p style='font-size: 10pt; line-height: 1.4; margin-bottom: 6pt; color: #0f172a; {align_style}'>{content}</p>"


def _image_html(image: ImageRef) -> str:
    # Görseli veri URI'si olarak HTML'e gömer / Embeds the image as a data URI
    if not image.data:
        return ""
    return f'<img src="{image.data_uri}" style="max-width: 100%;"/>'


def _table_html(cells: list[Block]) -> str:
    """Cells sharing a `table_id`, as one real `<table>` instead of one flowing box per cell.

    Same technique as `html_writer.py`'s `_render_table`, using this module's own span renderer
    so a translated cell keeps its bold/italic runs. `insert_htmlbox` (MuPDF's Story engine)
    renders `<table>` markup directly, so this needs no manual row-height layout - it goes
    through the same insertion path as every other block.
    """
    rows: dict[int, dict[int, Block]] = {}
    for cell in cells:
        rows.setdefault(cell.table_row, {})[cell.table_col] = cell

    rows_html: list[str] = []
    for row_index in sorted(rows):
        cells_html: list[str] = []
        for col_index in sorted(rows[row_index]):
            cell = rows[row_index][col_index]
            lines_html = ["".join(_span_to_html(s) for s in line.spans) for line in cell.lines]
            content = "<br/>".join(s for s in lines_html if s) or html.escape(cell.text.strip())
            cells_html.append(f'<td style="border: 1px solid #cbd5e1; padding: 4pt 6pt;">{content}</td>')
        rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    return f'<table style="border-collapse: collapse; width: 100%;">{"".join(rows_html)}</table>'


def _draw_flowing_page(pdf: pymupdf.Document, page_data: Page) -> None:
    # Akışkan metinli sayfayı PDF'e çizer / Draws text-flow page into PDF safely
    #
    # Iterates content_in_reading_order() rather than blocks_in_reading_order(): the latter
    # skips page_data.images entirely, which is how a DOCX-sourced PDF (this is the path a
    # geometry-less page takes - see has_layout in generate_pdf_from_docir) silently dropped
    # every embedded image. Measured in tools/audit/faz2_candidates.py: docx->pdf carried 100%
    # of the words and 0 of 1 images.
    usable_width = _A4_WIDTH - (2 * _MARGIN)
    max_y = _A4_HEIGHT - _MARGIN
    page = pdf.new_page(width=_A4_WIDTH, height=_A4_HEIGHT)
    curr_y = _MARGIN
    table_buffer: list[Block] = []
    open_table_id: int | None = None

    def insert(b_html: str, item: Block | ImageRef | None) -> None:
        nonlocal page, curr_y
        if not b_html:
            return
        if curr_y >= max_y - 36.0:
            page = pdf.new_page(width=_A4_WIDTH, height=_A4_HEIGHT)
            curr_y = _MARGIN

        rect = pymupdf.Rect(_MARGIN, curr_y, _MARGIN + usable_width, max_y)
        try:
            res = page.insert_htmlbox(rect, b_html)
            spare = res[0] if isinstance(res, (tuple, list)) else res
            if spare is not None and spare >= 0:
                curr_y += max(18.0, rect.height - spare + 6.0)
            else:
                page = pdf.new_page(width=_A4_WIDTH, height=_A4_HEIGHT)
                curr_y = _MARGIN
                rect = pymupdf.Rect(_MARGIN, curr_y, _MARGIN + usable_width, max_y)
                page.insert_htmlbox(rect, b_html)
                curr_y += 26.0
        except (RuntimeError, ValueError, OverflowError):
            # MuPDF çizim hatasında güvenli düz metin bas / Safe fallback
            if item is not None and not isinstance(item, ImageRef):
                page.insert_text(pymupdf.Point(_MARGIN, curr_y + 12), item.text[:120])
            curr_y += 20.0

    def flush_table() -> None:
        nonlocal open_table_id
        if table_buffer:
            insert(_table_html(table_buffer), None)
            table_buffer.clear()
        open_table_id = None

    # table_row/table_col are only populated by pdf_reader.py and docx_reader.py so far - a
    # TABLE block without a real grid position (epub_reader.py does not fill these in yet) falls
    # back to being drawn as its own box, same as before, rather than being grouped at the wrong
    # position (see html_writer.py's identical guard and the regression it caught).
    for item in page_data.content_in_reading_order():
        if isinstance(item, ImageRef):
            flush_table()
            insert(_image_html(item), item)
            continue
        if item.role == BlockRole.TABLE and item.table_row >= 0 and item.table_col >= 0:
            if open_table_id is not None and item.table_id != open_table_id:
                flush_table()
            table_buffer.append(item)
            open_table_id = item.table_id
            continue
        flush_table()
        insert(_block_html(item), item)

    flush_table()


def _draw_positioned_page(pdf: pymupdf.Document, page_data: Page) -> None:
    # Koordinatlı sayfayı PDF'e çizer / Draws coordinate-based page into PDF
    w = page_data.width if page_data.width > 0 else _A4_WIDTH
    h = page_data.height if page_data.height > 0 else _A4_HEIGHT
    page = pdf.new_page(width=w, height=h)

    for block in page_data.blocks_in_reading_order():
        b_html = _block_html(block)
        if not b_html:
            continue
        if block.bbox.width > 0 and block.bbox.height > 0:
            rect = pymupdf.Rect(block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1)
            with contextlib.suppress(RuntimeError, ValueError, OverflowError):
                page.insert_htmlbox(rect, b_html)

    # Same gap as _draw_flowing_page's, for the positioned case: without this, any source that
    # reaches this path with images (a real bbox per picture) loses every one of them.
    for image in page_data.images:
        if not image.data or image.bbox.width <= 0 or image.bbox.height <= 0:
            continue
        rect = pymupdf.Rect(image.bbox.x0, image.bbox.y0, image.bbox.x1, image.bbox.y1)
        with contextlib.suppress(RuntimeError, ValueError):
            page.insert_image(rect, stream=base64.b64decode(image.data))


def generate_pdf_from_docir(doc: Document, out_path: str | Path) -> None:
    # DocIR dokümanından yeni PDF oluşturur / Generates new PDF from DocIR
    pdf = pymupdf.open()
    has_layout = any(
        page.width > 0 and any(b.bbox.width > 0 for b in page.blocks)
        for page in doc.pages
    )

    for page_data in doc.pages:
        if has_layout:
            _draw_positioned_page(pdf, page_data)
        else:
            _draw_flowing_page(pdf, page_data)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(out))
    pdf.close()


def _reflow_block_html(block: Block, *, break_before: bool = False) -> str:
    """A block as HTML for the Story reflow, using the block's real size and alignment.

    Unlike `_block_html`, this trusts the reader-resolved font size (EPUB CSS) instead of
    substituting fixed 18/13/10pt — that substitution is exactly what flattened headings and
    lost the source's typography. `align` is applied here as well as the inline span sizes.

    `break_before` is the caller's decision, not this function's: a page break belongs at a chapter
    boundary, which is the first block of a spine document. Putting one on every heading is what
    gave a 436-page rebuild 105 sparse pages — each table-of-contents line and each poem-form
    heading started a page of its own.
    """
    lines_html: list[str] = []
    for line in block.lines:
        line_str = "".join(_span_to_html(span) for span in line.spans)
        if line_str:
            lines_html.append(line_str)
    content = "<br/>".join(lines_html) if lines_html else html.escape(block.text.strip()).replace("\n", "<br/>")
    if not content.strip():
        return ""

    size = block.dominant_style().size or 12.0
    align_style = f"text-align: {block.align}; " if block.align and block.align != "left" else ""
    brk = "page-break-before: always;" if break_before else ""

    if block.role == BlockRole.TITLE:
        return f"<h1 style='font-size: {size:.1f}pt; {align_style}{brk}'>{content}</h1>"
    if block.role == BlockRole.HEADING:
        return f"<h2 style='font-size: {size:.1f}pt; {align_style}{brk}'>{content}</h2>"
    if block.role == BlockRole.CODE:
        return f"<pre style='font-size: {size:.1f}pt; {align_style}'>{content}</pre>"
    return f"<p style='font-size: {size:.1f}pt; {align_style}'>{content}</p>"


def generate_reflowed_pdf_from_docir(doc: Document, out_path: str | Path) -> None:
    """Build a flowing PDF from a reflowable document (EPUB), keeping chapter breaks.

    MuPDF's own `layout()` re-flows an EPUB but ignores `page-break-before`, so chapter headings
    land mid-page (a chapter titled "CHAPTER II" at y=472 of an 842pt page). The `Story` API does
    honour page-breaks, so each heading starts a fresh page. Images the EPUB reader extracted are
    inlined as data URIs (Story ignores file paths but resolves data URIs), so figures survive
    the rebuild too.

    The first heading must NOT carry `page-break-before`: MuPDF's Story hangs on a break before
    its very first element, so the initial title is emitted without the break.
    """
    from pymupdf import Story

    # Build one HTML flow across all pages (EPUB pages are spine XHTML files, not physical pages).
    # A page break goes on the first block of a spine document - a real chapter start - and nowhere
    # else. The document's first block never gets one: MuPDF's Story hangs on a break before its
    # very first element, which is why the old code stripped it back out afterwards.
    chunks: list[str] = []
    first_content = True
    for page_data in doc.pages:
        starts_part = True
        for item in page_data.content_in_reading_order():
            if isinstance(item, ImageRef):
                if item.data:
                    chunks.append(f'<img src="{item.data_uri}" style="max-width: 100%;"/>')
                first_content = False
                starts_part = False
                continue
            block_html = _reflow_block_html(item, break_before=starts_part and not first_content)
            if not block_html:
                continue
            first_content = False
            starts_part = False
            chunks.append(block_html)

    story = Story(html="".join(chunks))
    mediabox = pymupdf.paper_rect(_EPUB_PDF_PAGE_SIZE)
    # Laid out into the whole sheet, the first line sat 8pt from the paper's edge and a page
    # that began with a heading started above the top of it. A book has margins; this gives it
    # the same ones on every side.
    frame = mediabox + (_PAGE_MARGIN, _PAGE_MARGIN, -_PAGE_MARGIN, -_PAGE_MARGIN)  # noqa: RUF005 - Rect arithmetic, not a list
    writer = pymupdf.DocumentWriter(str(out_path), "")
    more = 1
    guard = 0
    while more and guard < 1000:
        dev = writer.begin_page(mediabox)
        more, _filled = story.place(frame)
        story.draw(dev)
        writer.end_page()
        guard += 1
    writer.close()
