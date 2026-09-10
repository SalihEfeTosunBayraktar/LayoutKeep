"""EPUB→çapraz-formatta görsel + metin sıralaması: görsel iki paragraf ARASINDA duruyor mu?"""
import os
from pathlib import Path
import sys
from _common import TMP, setup

setup()
import zipfile




from layoutkeep.readers.epub_reader import read_epub

OUT = str(Path(TMP) / "imgpos.epub")

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

container = b"""<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

opf = b"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">x</dc:identifier><dc:title>ImgPos</dc:title><dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="img" href="fig.png" media-type="image/png"/>
    <item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>"""

# Gorsel iki paragrafin ARASINDA: beklenen siralamalar p1 -> GORSEL -> p2
chap = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>t</title></head>
<body>
  <p>PARAGRAPH ONE before the figure.</p>
  <div><img src="fig.png" alt="Alt text of figure"/></div>
  <p>PARAGRAPH TWO after the figure.</p>
</body>
</html>""".encode()

with zipfile.ZipFile(OUT, "w") as z:
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", container)
    z.writestr("OEBPS/content.opf", opf)
    z.writestr("OEBPS/chap1.xhtml", chap)
    z.writestr("OEBPS/fig.png", PNG)

doc = read_epub(OUT)
page = doc.pages[0]
print("=== content_in_reading_order (beklenen: p1 -> ImageRef -> p2) ===")
for item in page.content_in_reading_order():
    kind = type(item).__name__
    txt = item.text[:45] if hasattr(item, "text") else f"<gorsel fmt={item.fmt}>"
    print(f"  {kind}: {txt!r}")
print("\nSONUC: gorsel sirasi sonda ise -> DUMMY_BBOX(0,0) yuzunden tum gorseller sayfa sonuna yigitiliyor.")
