"""Reading and writing documents for the desktop run, and cutting a page range out of them.

Masaüstü koşusu için belge okur/yazar; seçilen sayfa aralığını çıktıya ve kaynak PDF'e uygular.
Reads and writes documents for the desktop run and applies the selected page range.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

from layoutkeep.core.docir import Document

#: Says "the caller handed over no layout model", so `read_document` keeps loading the installed
#: one by itself while `TranslationWorker._run` - which has to record whether a model was in hand - passes the very
#: detector it read with instead of loading a 171 MB model a second time.
_UNSET = object()


def load_layout_detector():
    from layoutkeep.ocr.layout_detector import load_detector

    return load_detector()


def read_document(path: Path, layout=_UNSET) -> Document:
    from layoutkeep.writers.converter import read_any_document

    # The local layout model when it is installed, as the CLI reads (cli._layout_detector): the
    # desktop application read every page without it, although the campaign measured every result
    # with it.
    if layout is _UNSET:
        layout = load_layout_detector()
    return read_any_document(path, layout=layout)


def write_document(doc: Document, source: Path, out: Path) -> list[Path]:
    from layoutkeep.writers.converter import write_any_document

    return write_any_document(doc, source, out)


def output_document(doc: Document, config) -> tuple[Document, set[int] | None]:
    """What the range promises, made true: the written file holds the selected pages.

    WHY THIS EXISTS: a page range used to narrow only what was *translated*, so choosing
    "40-60" produced a translation of those pages inside a copy of the whole book - reported as
    "shouldn't it output only the range I selected?". The project still keeps every page (the
    reviewer needs the rest, and re-exporting must not silently shorten the document), so the
    range is applied to a copy used for writing, not to the document that is saved.

    Sayfa aralığı artık çıktıyı da daraltır; kaydedilen proje belgenin tamamını korur.
    """
    if not (config.page_range and doc.pages):
        return doc, None

    from layoutkeep.core.range_helper import filter_document_by_pages, parse_page_range

    selected = parse_page_range(config.page_range, len(doc.pages))
    if len(selected) >= len(doc.pages):
        return doc, None

    subset = filter_document_by_pages(doc, selected)
    # The verification pass pairs source page N with output page N through `source_ref`, so the
    # kept pages are renumbered to their position inside the slice. They are deep-copied first:
    # filter_document_by_pages shares the Page objects with the project's document, and
    # renumbering those in place would corrupt the saved project.
    pages = []
    for index, page in enumerate(subset.pages):
        copied = copy.deepcopy(page)
        copied.source_ref = str(index)
        pages.append(copied)
    return replace(subset, pages=pages), selected


def source_slice(src: Path, selected: set[int], destination: Path) -> Path | None:
    """The selected pages of the source, as their own PDF, so verification compares like with like.

    A subset output cannot be checked against the full source: page 1 of the output is not page 1
    of the book, and every loss rule would read the wrong pair.
    """
    if src.suffix.lower() != ".pdf":
        return None
    import pymupdf

    with pymupdf.open(str(src)) as source:
        out = pymupdf.open()
        try:
            for number in sorted(selected):
                if 1 <= number <= source.page_count:
                    out.insert_pdf(source, from_page=number - 1, to_page=number - 1)
            if out.page_count in (0, source.page_count):
                return None
            out.save(str(destination))
        finally:
            out.close()
    return destination
