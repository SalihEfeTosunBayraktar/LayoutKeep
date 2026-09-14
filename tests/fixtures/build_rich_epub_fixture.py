"""Rich EPUB fixture: chapter with a real chart image, a table, bold/italic, list.

Same hand-built-zipfile approach as build_epub_fixture.py, so the bytes stay controlled.
The chart is the same chart_png() the other rich fixtures use.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


def _chart_png() -> bytes:
    img = Image.new("RGB", (440, 280), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 439, 279), outline="#0f172a", width=2)
    base_y, x0 = 240, 30
    d.line((x0, 16, x0, base_y), fill="#0f172a", width=3)
    d.line((x0, base_y, 420, base_y), fill="#0f172a", width=3)
    for i, bh in enumerate([52, 98, 72, 120, 84]):
        x = 50 + i * 72
        d.rectangle((x, base_y - bh, x + 52, base_y), fill="#2563eb")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


CONTAINER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

CONTENT_OPF = b"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:abcdef01-2345-6789-abcd-ef0123456789</dc:identifier>
    <dc:title>Rich Field Guide</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="img1" href="images/chart.png" media-type="image/png"/>
  </manifest>
  <spine toc="ncx"><itemref idref="chap1"/></spine>
</package>"""

TOC_NCX = b"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:abcdef01-2345-6789-abcd-ef0123456789"/></head>
  <docTitle><text>Rich Field Guide</text></docTitle>
  <navMap>
    <navPoint id="navpoint-1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="chap1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>"""

CHAP1_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head><title>Chapter 1</title></head>
<body>
<h1>The Field Campaign</h1>
<p>The <b>measurement</b> team ran a three-cell campaign for <i>1200 cycles</i> at a
constant 25 degrees with a 0.5 C discharge rate.</p>
<p>The chart below summarises the retained capacity per cell after the campaign.</p>
<p><img src="images/chart.png" alt="Capacity chart" title="Capacity chart"/></p>
<table>
<tr><td><b>Cell</b></td><td><b>Cycles</b></td><td><b>Capacity</b></td></tr>
<tr><td>A-101</td><td>500</td><td>92 percent</td></tr>
<tr><td>A-102</td><td>800</td><td>88 percent</td></tr>
<tr><td>A-103</td><td>1200</td><td>71 percent</td></tr>
</table>
<p>Two cells passed; one is flagged for review because it sits at the threshold.</p>
</body>
</html>"""


def build_rich_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", zipfile.ZIP_STORED)
        for name, data in (
            ("META-INF/container.xml", CONTAINER_XML),
            ("OEBPS/content.opf", CONTENT_OPF),
            ("OEBPS/toc.ncx", TOC_NCX),
            ("OEBPS/chap1.xhtml", CHAP1_XHTML),
            ("OEBPS/images/chart.png", _chart_png()),
        ):
            zf.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED)


if __name__ == "__main__":
    out = Path(__file__).parent
    build_rich_epub(out / "rich_book.epub")
    print(f"built: rich_book.epub in {out}")
