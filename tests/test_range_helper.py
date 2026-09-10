"""Unit tests for range_helper: parsing page intervals and filtering documents."""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.core.range_helper import filter_document_by_pages, parse_page_range


def test_parse_page_range_intervals():
    # Tekil ve aralık dizgilerini doğru ayrıştırma / Parses intervals correctly
    assert parse_page_range("1-3", 10) == {1, 2, 3}
    assert parse_page_range("1, 3, 5", 10) == {1, 3, 5}
    assert parse_page_range("2-4, 7-9", 10) == {2, 3, 4, 7, 8, 9}
    assert parse_page_range("5-2", 10) == {2, 3, 4, 5}  # Ters aralık


def test_parse_page_range_bounds_and_defaults():
    # Sınır aşımları ve varsayılan tüm sayfalar / Bounds check and fallback to all
    assert parse_page_range("8-15", 10) == {8, 9, 10}
    assert parse_page_range("all", 5) == {1, 2, 3, 4, 5}
    assert parse_page_range("", 4) == {1, 2, 3, 4}
    assert parse_page_range("invalid", 3) == {1, 2, 3}


def test_filter_document_by_pages():
    # Dokümandan yalnızca seçilen sayfaları tutma / Keeps only selected pages
    pages = [
        Page(
            number=i,
            width=100.0,
            height=200.0,
            blocks=[
                Block(
                    id=f"b{i}",
                    role=BlockRole.BODY,
                    bbox=BBox(0, 0, 10, 10),
                    lines=[Line(spans=[Span(text=f"Page {i}", bbox=BBox(0, 0, 10, 10), style=Style())])],
                )
            ],
        )
        for i in range(1, 6)
    ]
    doc = Document(pages=pages)

    filtered = filter_document_by_pages(doc, {2, 4})
    assert len(filtered.pages) == 2
    assert [p.number for p in filtered.pages] == [2, 4]
