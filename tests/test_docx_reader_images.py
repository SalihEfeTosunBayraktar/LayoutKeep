"""A DOCX carries pictures, and reading one has to bring them out.

`readers/docx_reader.py` had no image handling at all: every figure in a Word document was gone
before the translation layer ever saw it, and every conversion out of DOCX produced a document
with no pictures. It went unnoticed because the format matrix reported it as the *writer*
dropping images - the reader it counts with could not see them either way
(docs/ENGINE-ARCHITECTURE.md, "What this measurement got wrong").
"""

from __future__ import annotations

import base64
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fixtures.build_docx_fixture import build_sample_docx

from layoutkeep.readers.docx_reader import read_docx

#: A real 2x3 PNG: distinguishable dimensions, so a size read back can be checked.
_PNG_2x3 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000020000000308060000003a4c76"
    "cf0000001849444154789c6360606060000000050001a5f6453d0000000049454e44ae426082"
)

_DRAWING = (
    "<w:p><w:r><w:drawing><wp:inline"
    ' xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' distT="0" distB="0" distL="0" distR="0">'
    '<wp:extent cx="1905000" cy="2857500"/>'
    '<wp:docPr id="1" name="Picture 1"/>'
    '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:blipFill><a:blip r:embed="rId99"/></pic:blipFill>'
    "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
)


def _docx_with_a_picture(path: Path) -> None:
    """The sample document, with a picture wired in the way Word wires one."""
    build_sample_docx(path)
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}

    document = parts["word/document.xml"].decode("utf-8")
    document = document.replace("</w:body>", _DRAWING + "</w:body>", 1)
    parts["word/document.xml"] = document.encode("utf-8")

    rels_name = "word/_rels/document.xml.rels"
    rels = parts[rels_name].decode("utf-8")
    rels = rels.replace(
        "</Relationships>",
        '<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/image" Target="media/image1.png"/>'
        "</Relationships>",
        1,
    )
    parts[rels_name] = rels.encode("utf-8")
    parts["word/media/image1.png"] = _PNG_2x3

    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)


def test_a_picture_in_a_docx_reaches_docir(tmp_path: Path) -> None:
    src = tmp_path / "with_picture.docx"
    _docx_with_a_picture(src)

    doc = read_docx(src)
    images = [image for page in doc.pages for image in page.images]
    assert images, "the picture never reached DocIR"

    image = images[0]
    assert base64.b64decode(image.data) == _PNG_2x3, "the bytes must arrive unchanged"
    assert image.fmt == "png"


def test_the_size_word_declared_is_kept(tmp_path: Path) -> None:
    """`wp:extent` is in EMU; DocIR works in points. 1905000 EMU is 150pt, 2857500 is 225pt."""
    src = tmp_path / "sized.docx"
    _docx_with_a_picture(src)

    image = next(image for page in read_docx(src).pages for image in page.images)
    assert round(image.bbox.width) == 150
    assert round(image.bbox.height) == 225


def test_a_document_with_no_pictures_gains_none(tmp_path: Path) -> None:
    src = tmp_path / "plain.docx"
    build_sample_docx(src)

    assert sum(len(page.images) for page in read_docx(src).pages) == 0
