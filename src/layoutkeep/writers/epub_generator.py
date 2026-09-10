"""EPUB generator: creates a fresh EPUB file from a DocIR Document for cross-format export.

DocIR dokümanından sıfırdan EPUB e-kitabı üreten çapraz format dışa aktarım modülü.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

from layoutkeep.core.docir import BlockRole, Document, ImageRef, Page


def _render_page_xhtml(page: Page, title: str, image_names: dict[int, str]) -> str:
    # Sayfa içeriğini XHTML olarak biçimlendirir / Formats page content as XHTML
    body_parts: list[str] = []
    for item in page.content_in_reading_order():
        if isinstance(item, ImageRef):
            name = image_names.get(id(item))
            if name:
                body_parts.append(f'<p><img src="{name}" alt=""/></p>')
            continue
        text = html.escape(item.text.strip()).replace(chr(10), "<br/>")
        if not text:
            continue
        if item.role == BlockRole.TITLE:
            body_parts.append(f"<h1>{text}</h1>")
        elif item.role == BlockRole.HEADING:
            body_parts.append(f"<h2>{text}</h2>")
        else:
            body_parts.append(f"<p>{text}</p>")

    if not body_parts:
        # A page with no content at all produces an empty <body>, and ebooklib parses every
        # chapter it writes: lxml raises "Document is empty" and the whole export fails. One
        # image-only page in a scanned report used to take the entire conversion down.
        body_parts.append(f'<p class="empty-page">{html.escape(title)}</p>')

    inner_content = "\n  ".join(body_parts)
    return (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<!DOCTYPE html>\n"
        "<html xmlns=\"http://www.w3.org/1999/xhtml\" lang=\"en\">\n"
        f"<head><title>{html.escape(title)}</title></head>\n"
        f"<body>\n  {inner_content}\n</body>\n"
        "</html>"
    )


def generate_epub_from_docir(doc: Document, out_path: str | Path) -> None:
    # DocIR dokümanından yeni EPUB oluşturur / Generates new EPUB from DocIR
    from ebooklib import epub

    book = epub.EpubBook()
    title_meta = doc.metadata.get("title") if isinstance(doc.metadata, dict) else None
    title = title_meta or Path(out_path).stem
    book.set_title(title)
    book.set_language(doc.target_lang or "en")

    chapters = []
    image_names: dict[int, str] = {}
    for page_number, page in enumerate(doc.pages, 1):
        for image_number, image in enumerate(page.images, 1):
            if not image.data:
                continue
            name = f"images/p{page_number:03d}_{image_number:02d}.{image.fmt}"
            image_names[id(image)] = name
            book.add_item(
                epub.EpubItem(
                    uid=f"img_{page_number:03d}_{image_number:02d}",
                    file_name=name,
                    media_type=f"image/{image.fmt}",
                    content=base64.b64decode(image.data),
                )
            )

    for idx, page in enumerate(doc.pages, 1):
        xhtml_content = _render_page_xhtml(page, f"{title} - Bölüm {idx}", image_names)
        chapter = epub.EpubHtml(
            title=f"Bölüm {idx}",
            file_name=f"chap_{idx:03d}.xhtml",
            lang=doc.target_lang or "en",
        )
        chapter.set_content(xhtml_content.encode("utf-8"))
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *chapters]

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out), book)
