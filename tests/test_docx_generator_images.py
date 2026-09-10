"""An image with no geometry still has a size, and Word needs to be told one.

DocIR is shaped for a page: everything carries a bounding box. A reflowable source has no
geometry to give - an EPUB image has a position in the flow and nothing else - so its box arrives
empty. The DOCX generator sized the drawing straight from that box, embedded the picture at
1 EMU by 1 EMU, and produced a document that contains the image and shows nothing.

Measured with `tools/audit/format_matrix.py`: epub -> docx, images 0 of 1.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core.docir import BBox, Document, ImageRef, Page
from layoutkeep.writers.docx_generator import generate_docx_from_docir

#: A real 2x3 PNG, so intrinsic width and height are distinguishable from each other.
_PNG_2x3 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000020000000308060000003a4c76"
    "cf0000001849444154789c6360606060000000050001a5f6453d0000000049454e44ae426082"
)

#: OOXML measures drawings in English Metric Units: 914400 to the inch.
_EMU_PER_INCH = 914400


def _document(bbox: BBox) -> Document:
    import base64

    image = ImageRef(
        bbox=bbox, data=base64.b64encode(_PNG_2x3).decode("ascii"), fmt="png", order=0
    )
    return Document(pages=[Page(number=1, width=595, height=842, images=[image], source_ref="0")])


def _extents(path: Path) -> list[tuple[int, int]]:
    """Every drawing's declared size, from the document's own XML."""
    import re

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "replace")
    return [
        (int(cx), int(cy))
        for cx, cy in re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', xml)
    ]


def test_an_image_without_geometry_is_given_its_own_size(tmp_path: Path) -> None:
    out = tmp_path / "noboxes.docx"
    generate_docx_from_docir(_document(BBox(0, 0, 0, 0)), out)

    sizes = _extents(out)
    assert sizes, "the drawing must be in the document"
    width, height = sizes[0]
    assert width > _EMU_PER_INCH // 100, f"width came out at {width} EMU, invisible"
    assert height > _EMU_PER_INCH // 100, f"height came out at {height} EMU, invisible"
    # The picture is 2x3, so it must be taller than it is wide - a square default would lose
    # the shape of every figure in the book.
    assert height > width


def test_a_box_the_source_did_give_is_respected(tmp_path: Path) -> None:
    """A PDF image has real geometry and it must win over anything intrinsic."""
    out = tmp_path / "boxed.docx"
    generate_docx_from_docir(_document(BBox(0, 0, 144, 72)), out)

    width, height = _extents(out)[0]
    assert width == 144 * (_EMU_PER_INCH // 72)
    assert height == 72 * (_EMU_PER_INCH // 72)
