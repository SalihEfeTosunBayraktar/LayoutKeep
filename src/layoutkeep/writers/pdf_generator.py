"""PDF generator: creates a new PDF from a DocIR Document for cross-format export.

DocIR dokümanından sıfırdan PDF üreten çapraz format dışa aktarım modülü.
"""

from __future__ import annotations

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


def _draw_flowing_page(pdf: pymupdf.Document, page_data: Page) -> None:
    # Akışkan metinli sayfayı PDF'e çizer / Draws text-flow page into PDF safely
    usable_width = _A4_WIDTH - (2 * _MARGIN)
    max_y = _A4_HEIGHT - _MARGIN
    page = pdf.new_page(width=_A4_WIDTH, height=_A4_HEIGHT)
    curr_y = _MARGIN

    for block in page_data.blocks_in_reading_order():
        b_html = _block_html(block)
        if not b_html:
            continue

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
            page.insert_text(pymupdf.Point(_MARGIN, curr_y + 12), block.text[:120])
            curr_y += 20.0


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


def _reflow_block_html(block: Block) -> str:
    """A block as HTML for the Story reflow, using the block's real size and alignment.

    Unlike `_block_html`, this trusts the reader-resolved font size (EPUB CSS) instead of
    substituting fixed 18/13/10pt — that substitution is exactly what flattened headings and
    lost the source's typography. `align` is applied here as well as the inline span sizes.
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

    if block.role == BlockRole.TITLE:
        return f"<h1 style='font-size: {size:.1f}pt; {align_style}page-break-before: always;'>{content}</h1>"
    if block.role == BlockRole.HEADING:
        return f"<h2 style='font-size: {size:.1f}pt; {align_style}page-break-before: always;'>{content}</h2>"
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
    chunks: list[str] = []
    first_content = True
    for page_data in doc.pages:
        for item in page_data.content_in_reading_order():
            if isinstance(item, ImageRef):
                if item.data:
                    chunks.append(f'<img src="{item.data_uri}" style="max-width: 100%;"/>')
                first_content = False
                continue
            block_html = _reflow_block_html(item)
            if not block_html:
                continue
            # Strip the page-break on the document's very first content chunk (Story hang guard).
            if first_content:
                block_html = block_html.replace("page-break-before: always; ", "").replace(
                    "page-break-before: always;", ""
                )
                first_content = False
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
