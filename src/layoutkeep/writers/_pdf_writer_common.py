"""Shared constants of the PDF writer: base-14 fonts, rotation tolerance, line height, rectangles.

PDF yazıcısının modüllerinin paylaştığı sabitler: temel 14 yazı tipi, dönüş toleransı, satır
yüksekliği ve dikdörtgen yardımcısı.
"""

from __future__ import annotations

import re
import string

import pymupdf
from fontTools.ttLib import TTLibError

from layoutkeep.core import tunables
from layoutkeep.core.docir import BBox

#: Draw each inline run at its own size instead of the block's. Off by default: it is the subject of
#: an A/B (the per-box instrument counts 6-15 boxes per document where a smaller run is drawn at its
#: block's size) and it can move line heights, so nothing changes for a user until that is measured.
_INLINE_SPAN_SIZES_KEY = "writer.inline_span_sizes"
_BOX_SLACK_KEY = "write.box_slack_pt"

#: Below this many degrees a block is treated as ordinary horizontal text - noise in pymupdf's
#: `dir` vector, not an actual rotation. Matches `pdf_reader.py`'s own tolerance.
_ROTATION_EPS = 0.5
#: `insert_htmlbox`'s line-height guess, reused for stacking a rotated block's lines.
#:
#: Read from the tunable rather than declared here, because the reader derives a scanned block's
#: font size so that size x this ratio reproduces the line pitch it measured off the page. The
#: two must agree or every scanned page is mis-sized, and 1.2 used to be written out separately
#: in both files with nothing enforcing it.
_LINE_HEIGHT_KEY = "merge.line_height_ratio"


def writer_line_height_ratio() -> float:
    """How tall a line is stacked, as a multiple of the font size. Read at use, so a changed
    setting is seen without reimporting the module."""
    return tunables.get(_LINE_HEIGHT_KEY)


#: PDF base-14 font names, keyed by (generic family, bold, italic). Fallback for the rotated-text
#: path (needs a real `pymupdf.Font`, not a CSS family name) and for any block whose font could
#: not be resolved to a real file at all - see `_FontResolver`.
_BASE14 = {
    ("sans-serif", False, False): "helv",
    ("sans-serif", True, False): "hebo",
    ("sans-serif", False, True): "heit",
    ("sans-serif", True, True): "hebi",
    ("serif", False, False): "tiro",
    ("serif", True, False): "tibo",
    ("serif", False, True): "tiit",
    ("serif", True, True): "tibi",
    ("monospace", False, False): "cour",
    ("monospace", True, False): "cobo",
    ("monospace", False, True): "coit",
    ("monospace", True, True): "cobi",
}

#: Characters kept in every subset regardless of what the document actually uses, so
#: `insert_htmlbox`'s own layout (wrapping, hyphenation fallback, whitespace) never hits a
#: missing glyph even when the translated text happens not to contain some of them.
_ALWAYS_KEEP_CHARS = string.ascii_letters + string.digits + string.punctuation + " \n"

_SUBSET_TAG_RE = re.compile(r"^[A-Z]{6}\+")

#: What a malformed or unusual font file (bad table, unsupported flavour, truncated data) raises
#: across fontTools' loading, instancing and subsetting - caught wherever a font resolved from
#: an untrusted source PDF or a bundled file on disk must not take the whole write down with it.
_FONT_LOAD_ERRORS = (TTLibError, OSError, ValueError, KeyError, AssertionError)


def _rect(bbox: BBox) -> pymupdf.Rect:
    return pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
