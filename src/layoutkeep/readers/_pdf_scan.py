"""Scanned pages: telling a searchable scan apart and reading a page through OCR.

Taranmış sayfalar: aranabilir taramayı ayırt eder ve sayfayı OCR ile okur.
"""

from __future__ import annotations

import pymupdf
from PIL import Image

from layoutkeep.core import tunables
from layoutkeep.ocr.layout_detector import LayoutDetector
from layoutkeep.ocr.layout_vlm import ChatFn
from layoutkeep.readers._pdf_common import _RawBlock, _RawPage
from layoutkeep.readers._pdf_images import _extract_images
from layoutkeep.readers.image_reader import (
    expected_characters,
    needs_higher_resolution,
    page_from_rendered_page,
)

#: Resolution the page is rasterised at before OCR. Measured on page 61 of
#: `computer-systems-Architecture.pdf` (a 600-DPI scan): 200 DPI recovered all 47 text boxes at
#: 0.96 mean confidence, while 300 DPI cost ~2x the pixels and garbled a line the lower
#: resolution read cleanly. Higher is not automatically better - the recognition model has its
#: own preferred glyph height.
_SCAN_OCR_DPI = 200.0

#: Resolution a badly-read page is rendered at for its second pass (see
#: `image_reader.needs_higher_resolution`). Page 54 of the same book is why: at 200 DPI a clean
#: line of type came out as "Sin os -ns ( s ms o ong", and at 300 it reads correctly, recovering
#: 9.4% more characters on that page. Across six pages the same change is worth only +1.5%, so
#: it is not the default - it is what a page gets when the cheap pass reports too much doubt.
_SCAN_OCR_RETRY_DPI = 300.0


def _ocr_at(
    page: pymupdf.Page,
    index: int,
    dpi: float,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
):
    """Rasterise `page` at `dpi` and hand the pixels to OCR."""
    pixmap = page.get_pixmap(dpi=int(dpi))
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    return page_from_rendered_page(
        image,
        number=index + 1,
        source_ref=str(index),
        dpi=dpi,
        width_pt=page.rect.width,
        height_pt=page.rect.height,
        classifier=classifier,
        layout=layout,
    )


#: Text render mode 3: glyphs that are laid out but not painted - the searchable layer a scanner
#: or archive.org puts over a page image.
_INVISIBLE_TEXT = 3


def _is_searchable_scan(page: pymupdf.Page, coverage: float) -> bool:
    """True when an image covers the page and most of its text is invisible.

    A searchable scan carries a full OCR text layer, so by text density it looks born digital;
    read that way, the writer removed the invisible layer and drew the translation over the
    scanned English, which is pixels and stays. What a reader actually sees is decided by
    visibility: when most characters are not painted, the page is its image. Two of the
    campaign's five books are built this way (archive.org "Text PDF"), and so were pages 4-10 of
    the NASA report.
    """
    if coverage < tunables.get("reader.scan_image_coverage_layer"):
        return False
    visible = invisible = 0
    for trace in page.get_texttrace():
        count = len(trace.get("chars", ()))
        if trace.get("type") == _INVISIBLE_TEXT:
            invisible += count
        else:
            visible += count
    return invisible > visible


#: A searchable scan's image is the page. Majority coverage is the lowest that can mean that; a
#: page with a picture beside invisible text is not a scan of the whole page.
_SCANNED_IMAGE_COVERAGE_FOR_LAYER = 0.5


def _read_scanned_page(
    page: pymupdf.Page,
    index: int,
    *,
    top_edge: float,
    bottom_edge: float,
    classifier: ChatFn | None = None,
    layout: LayoutDetector | None = None,
) -> _RawPage:
    """A page with no text layer: rasterise it and let OCR find the text.

    Without this a scanned PDF reads as zero blocks and the app reports that there is nothing to
    translate - which is what `computer-systems-Architecture.pdf` (524 pages, no text layer at
    all) did. The OCR itself lives in `readers/image_reader.py`; this only supplies the pixels,
    because CONTRACT.md keeps the pymupdf import on this side of the boundary.
    """
    ocr_page = _ocr_at(page, index, _SCAN_OCR_DPI, classifier, layout)
    if needs_higher_resolution(ocr_page):
        # Enough of the page came back doubtful to be worth the extra pixels. Both passes are
        # kept and the better one wins, judged on how much text each recovered rather than on
        # how sure it sounds: page 61 of this book reads a line correctly at 200 and garbles it
        # at 300, and on page 451 the surer pass is the one that read 65 characters fewer.
        retry = _ocr_at(page, index, _SCAN_OCR_RETRY_DPI, classifier, layout)
        if expected_characters(retry) > expected_characters(ocr_page):
            ocr_page = retry
    ocr_page.scanned = True
    # The scan itself is the page's only picture; writers that rebuild the document need it, and
    # the pdf writer needs it to paint over the burnt-in source text.
    ocr_page.images = _extract_images(page)

    raw_blocks = [
        _RawBlock(
            block=b,
            top_margin=b.bbox.y0 <= top_edge,
            bottom_margin=b.bbox.y1 >= bottom_edge,
        )
        for b in ocr_page.blocks
    ]
    return _RawPage(page=ocr_page, blocks=raw_blocks, images=[img.bbox for img in ocr_page.images])
