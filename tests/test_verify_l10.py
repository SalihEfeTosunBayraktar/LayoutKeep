"""L10: text that ended up inside a picture.

The case that made this criterion necessary: a Wikipedia article whose text block wraps *around* a
photograph. The reader reports the block as the bounding box of those wrapped lines, the writer
re-flows the translation across the whole box, and the first lines land on the picture - 87 words
in the run that reached the published comparison site, with L7 reporting nothing, because no
letter of one block was over a letter of another.

The check is geometric, so these tests build pages rather than strings: a page with a real image
and a word on it, a page whose image *is* the scan.
"""

from __future__ import annotations

import pymupdf

from layoutkeep.verify import words_over_figures


def _png(width: int = 40, height: int = 40, grey: float = 0.6) -> bytes:
    """A small real image: `get_image_info` sees raster images, not drawn rectangles."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height))
    pixmap.set_rect(pixmap.irect, (int(grey * 255), int(grey * 255), int(grey * 255)))
    return pixmap.tobytes("png")


def _page_with_picture(path, *, picture: tuple[float, float, float, float], text_at: tuple[float, float],
                       as_background: bool = False) -> str:
    document = pymupdf.open()
    page = document.new_page(width=595.0, height=842.0)
    if as_background:
        picture = (0.0, 0.0, 595.0, 842.0)
    page.insert_image(pymupdf.Rect(*picture), stream=_png())
    page.insert_text(text_at, "Gutenberg", fontsize=11)
    document.save(str(path))
    document.close()
    return str(path)


def test_a_word_inside_a_picture_is_reported(tmp_path):
    path = _page_with_picture(
        tmp_path / "on_picture.pdf",
        picture=(300, 120, 550, 320),
        text_at=(320, 160),
    )

    with pymupdf.open(path) as document:
        page = document[0]
        found = words_over_figures(page, page.get_text("words"))

    assert len(found) == 1


def test_a_word_beside_a_picture_is_not(tmp_path):
    path = _page_with_picture(
        tmp_path / "beside.pdf",
        picture=(300, 120, 550, 320),
        text_at=(60, 160),
    )

    with pymupdf.open(path) as document:
        page = document[0]
        found = words_over_figures(page, page.get_text("words"))

    assert found == []


def test_a_scanned_page_is_not_a_figure(tmp_path):
    """A scan is one image with the translation written over it on purpose."""
    path = _page_with_picture(
        tmp_path / "scan.pdf",
        picture=(0, 0, 595, 842),
        text_at=(120, 400),
        as_background=True,
    )

    with pymupdf.open(path) as document:
        page = document[0]
        found = words_over_figures(page, page.get_text("words"))

    assert found == []

