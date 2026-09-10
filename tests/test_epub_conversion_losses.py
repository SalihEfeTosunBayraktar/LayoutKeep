"""What an EPUB loses when it is rebuilt as something else.

Measured on a fixture carrying one of each thing a real book carries. Before these were fixed:
one of three pictures survived, the caption under a figure and the header row of a table were
not in the document at all, and the pictures that did survive were drawn after the last
paragraph of the chapter, on top of each other.

None of it was reported. The output simply came out shorter than the book, which is the worst
way for a converter to fail (docs/CONTRACT.md D6).
"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest

from layoutkeep.core.docir import BlockRole, ImageRef

pytest.importorskip("ebooklib")
pytest.importorskip("PIL")


def _png(size: tuple[int, int], colour: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Ch</title></head><body>
  <h1>Chapter One</h1>
  <p>The first paragraph.</p>
  <figure>
    <img src="images/figure.png" alt="A figure"/>
    <figcaption>Figure 1: a rectangle.</figcaption>
  </figure>
  <p>A paragraph after the figure.</p>
  <div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><image
       xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="images/plate.png"/></svg></div>
  <table><tr><th>Plate</th><th>Cycles</th></tr><tr><td>A-1</td><td>10</td></tr></table>
</body></html>
"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">fixture</dc:identifier><dc:title>Fixture</dc:title>
    <dc:language>en</dc:language><meta name="cover" content="cover-img"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="fig" href="images/figure.png" media-type="image/png"/>
    <item id="plate" href="images/plate.png" media-type="image/png"/>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/></spine>
</package>
"""

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="OEBPS/content.opf"
  media-type="application/oebps-package+xml"/></rootfiles></container>
"""


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/chapter1.xhtml", CHAPTER)
        zf.writestr("OEBPS/images/cover.png", _png((60, 80), (30, 60, 160)))
        zf.writestr("OEBPS/images/figure.png", _png((40, 24), (200, 90, 40)))
        zf.writestr("OEBPS/images/plate.png", _png((40, 20), (40, 160, 90)))
    return path


def _read(path: Path):
    from layoutkeep.writers.converter import read_any_document

    return read_any_document(path)


def _colour(image: ImageRef) -> tuple[int, int, int]:
    from PIL import Image

    return Image.open(io.BytesIO(base64.b64decode(image.data))).convert("RGB").getpixel((1, 1))


def test_every_picture_in_the_book_reaches_the_document(book: Path) -> None:
    """One of three used to: the SVG-wrapped one and the cover were never seen."""
    doc = _read(book)
    colours = {_colour(image) for page in doc.pages for image in page.images}

    assert (200, 90, 40) in colours, "the plain <img> figure"
    assert (40, 160, 90) in colours, "the picture wrapped in <svg><image>"
    assert (30, 60, 160) in colours, "the cover, declared in the package file only"


def test_the_cover_is_not_carried_twice(book: Path, tmp_path: Path) -> None:
    """A book whose first page shows the cover as an <img> would otherwise get two of it."""
    doc = _read(book)
    data = [image.data for page in doc.pages for image in page.images]

    assert len(data) == len(set(data))


def test_text_a_reader_can_see_is_text_the_document_has(book: Path) -> None:
    doc = _read(book)
    text = " ".join(b.text for _, b in doc.iter_blocks())

    assert "Figure 1: a rectangle." in text, "figcaption"
    assert "Plate" in text and "Cycles" in text, "table header cells"


def test_a_header_cell_is_a_table_cell_and_a_caption_is_a_caption(book: Path) -> None:
    doc = _read(book)
    roles = {b.text: b.role for _, b in doc.iter_blocks()}

    assert roles["Plate"] == BlockRole.TABLE
    assert roles["Figure 1: a rectangle."] == BlockRole.CAPTION


def test_a_figure_stays_with_the_text_it_belongs_to(book: Path) -> None:
    """An EPUB has no positions at all, so sorting pictures by where they sit put every one of
    them after every paragraph - at the end of the chapter, away from its caption."""
    doc = _read(book)
    page = doc.pages[0]
    flow = page.content_in_reading_order()

    kinds = ["image" if isinstance(item, ImageRef) else item.text for item in flow]
    figure_at = kinds.index("image")
    caption_at = kinds.index("Figure 1: a rectangle.")

    assert kinds.index("The first paragraph.") < figure_at < caption_at
    assert kinds[-1] != "image", "pictures no longer pile up at the end"


def test_a_project_file_written_before_this_still_loads(tmp_path: Path) -> None:
    """`order` is new on ImageRef; a project saved without it must not fail to open."""
    import json

    from layoutkeep.core.docir import load_project

    project = tmp_path / "old.lkproj"
    project.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": [
                    {
                        "number": 1,
                        "width": 0,
                        "height": 0,
                        "blocks": [],
                        "images": [
                            {"bbox": {"x0": 0, "y0": 0, "x1": 1, "y1": 1}, "data": "", "fmt": "png"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    doc = load_project(project)

    assert doc.pages[0].images[0].order == -1
