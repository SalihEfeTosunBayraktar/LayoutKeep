"""Compose a bilingual PDF: the source page and its translation in one file.

WHY THIS EXISTS: the comparison site shows source and translation side by side, but the PDF that
comes out of a run holds only the translation - the reader who wants to check a sentence against
the original has to open two files and keep them aligned by hand. BabelDOC offers the same feature
(`--use-alternating-pages-dual`, side by side by default), and it was the top item on this
project's roadmap.

WHY IT IS A SEPARATE STEP, NOT PART OF THE WRITER: the lossless audit pairs source page N with
output page N (L1-L10 all read that pairing). A dual document breaks it - side by side changes the
page width, alternating doubles the page count - so the *translated* PDF must stay exactly what it
was. Composing is therefore done afterwards, on two finished files: the translation pipeline and
every audit number are untouched by this module.
"""

from __future__ import annotations

from pathlib import Path

#: Side by side on one page (default) or the translation after each source page.
MODES = ("side", "alternate")

#: A hairline between the two halves, so a page with a white margin does not look like one page.
_SEPARATOR_WIDTH = 0.6
_SEPARATOR_GREY = 0.62


def compose_dual(source: Path, translated: Path, out: Path, mode: str = "side") -> int:
    """Write `source` and `translated` into one PDF at `out`; return the pages written.

    Only the pages both documents have are composed: a run that was interrupted has fewer
    translated pages than the source, and silently emitting a document shorter than either would
    be the kind of quiet loss this project exists to avoid - so the count is returned and printed
    by the caller.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}, expected one of {MODES}")

    import pymupdf

    with pymupdf.open(str(source)) as src, pymupdf.open(str(translated)) as tr:
        pages = min(src.page_count, tr.page_count)
        if pages == 0:
            raise ValueError("nothing to compose: one of the documents has no pages")
        document = pymupdf.open()
        try:
            if mode == "alternate":
                for index in range(pages):
                    document.insert_pdf(src, from_page=index, to_page=index)
                    document.insert_pdf(tr, from_page=index, to_page=index)
            else:
                for index in range(pages):
                    left = src[index].rect
                    right = tr[index].rect
                    height = max(left.height, right.height)
                    page = document.new_page(width=left.width + right.width, height=height)
                    page.show_pdf_page(
                        pymupdf.Rect(0, 0, left.width, height), src, index, keep_proportion=True
                    )
                    page.show_pdf_page(
                        pymupdf.Rect(left.width, 0, left.width + right.width, height),
                        tr,
                        index,
                        keep_proportion=True,
                    )
                    separator = left.width
                    page.draw_line(
                        pymupdf.Point(separator, 0),
                        pymupdf.Point(separator, height),
                        color=(_SEPARATOR_GREY, _SEPARATOR_GREY, _SEPARATOR_GREY),
                        width=_SEPARATOR_WIDTH,
                    )
            # Ne çevrildi, neyle: çift dilli dosya da aynı koşunun ürünü, kaydı çevrilmiş
            # dosyadan devralır (pdf_writer.copy_provenance).
            from layoutkeep.writers.pdf_writer import copy_provenance

            copy_provenance(tr, document)
            document.save(str(out), garbage=4, deflate=True)
        finally:
            document.close()
    return pages
