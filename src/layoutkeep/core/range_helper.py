"""Range helper: parses page/chapter range strings and filters Document pages.

Sayfa veya bölüm aralık dizgilerini (örn: '1-5, 8') ayrıştıran ve DocIR dokümanını filtreleyen yardımcı modül.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Document, Page

_RANGE_PATTERN = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def parse_page_range(spec: str, total_pages: int) -> set[int]:
    # Aralık metnini 1-tabanlı sayfa numaraları kümesine çevirir / Parses range string to 1-based page numbers
    spec = spec.strip()
    if not spec or spec.lower() in ("all", "tümü", "*"):
        return set(range(1, total_pages + 1))

    selected: set[int] = set()
    parts = spec.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = _RANGE_PATTERN.match(part)
        if not match:
            continue
        start_str, end_str = match.groups()
        start = int(start_str)
        end = int(end_str) if end_str is not None else start
        if start > end:
            start, end = end, start

        for p in range(start, end + 1):
            if 1 <= p <= total_pages:
                selected.add(p)

    return selected if selected else set(range(1, total_pages + 1))


def block_ids_for_pages(doc: Document, pages: set[int]) -> set[str]:
    """Ids of the blocks living on the selected pages.

    This is how a page range should be applied: narrow what gets *translated*, not what the
    document *contains*. Dropping pages from the Document instead means the saved project holds
    only the selected pages, so the review editor cannot show the rest and re-exporting from the
    project silently produces a shorter document than the source (CONTRACT.md, D5).

    Sayfa aralığını uygularken belgeden sayfa silinmez; yalnızca çevrilecek bloklar seçilir.
    """
    selected: set[str] = set()
    for index, page in enumerate(doc.pages, start=1):
        number = page.number if page.number > 0 else index
        if number in pages or index in pages:
            selected.update(block.id for block in page.blocks)
    return selected


def filter_document_by_pages(doc: Document, pages: set[int]) -> Document:
    """Return a copy holding only the selected pages.

    WARNING: this discards the other pages entirely. Do not use it to apply a page range to a
    translation job - the saved project would keep only the selected pages and the reviewer
    would lose every other page of the document. Use `block_ids_for_pages` for that.
    """
    # Dokümanı yalnızca seçilen sayfa numaralarını içerecek şekilde filtreler / Filters document pages
    if not doc.pages or not pages:
        return doc

    filtered_pages: list[Page] = []
    for idx, page in enumerate(doc.pages, start=1):
        num = page.number if page.number > 0 else idx
        if num in pages or idx in pages:
            filtered_pages.append(page)

    if not filtered_pages:
        filtered_pages = doc.pages

    return Document(
        pages=filtered_pages,
        source_path=doc.source_path,
        source_format=doc.source_format,
        source_lang=doc.source_lang,
        target_lang=doc.target_lang,
        metadata=dict(doc.metadata),
    )
