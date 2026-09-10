"""Uç durum EPUB fixture'i: SVG-sarmalı görsel, OPF kapak, <th>, <figcaption>, görsel yerleşimi."""
import os
from pathlib import Path
import sys
from _common import TMP, setup

setup()
import zipfile




from layoutkeep.readers.epub_reader import read_epub

OUT = str(Path(TMP) / "edge.epub")

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

container = b"""<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">x</dc:identifier>
    <dc:title>Edge Cases</dc:title>
    <dc:language>en</dc:language>
    <meta name="cover" content="cover-img"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>
    <item id="svg-img" href="fig.png" media-type="image/png"/>
    <item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>""".encode()

# NOT: <img> ile (chap ortasinda), SVG icine sarilmis <image>, <th> hücresi, <figcaption>
chap = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>t</title></head>
<body>
  <p>First paragraph before the figure.</p>
  <div class="illustration">
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">
      <image xlink:href="fig.png" width="100" height="100"/>
    </svg>
    <figcaption>A caption under the SVG figure.</figcaption>
  </div>
  <p>Second paragraph after the figure.</p>
  <table><tr><th>Header Cell Text</th><td>Body cell</td></tr></table>
  <p>Third paragraph.</p>
</body>
</html>""".encode()

with zipfile.ZipFile(OUT, "w") as z:
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", container)
    z.writestr("OEBPS/content.opf", opf)
    z.writestr("OEBPS/chap1.xhtml", chap)
    z.writestr("OEBPS/cover.png", PNG)
    z.writestr("OEBPS/fig.png", PNG)

doc = read_epub(OUT)
page = doc.pages[0]
print("=== BLOKLAR (okuma sirasi) ===")
for b in page.blocks_in_reading_order():
    print(f"  order={b.order} id={b.id} role={b.role.value} text={b.text[:60]!r}")
print(f"\n=== ImageRef sayisi: {len(page.images)} (beklenen 2: cover + svg-icinde-fig) ===")
for i in page.images:
    print(f"  ImageRef fmt={i.fmt} bbox={i.bbox} data_len={len(i.data)}")

print("\n=== content_in_reading_order ciktisi ===")
for item in page.content_in_reading_order():
    kind = type(item).__name__
    text = item.text[:50] if hasattr(item, "text") else f"<gorsel data_len={len(item.data)}>"
    print(f"  {kind}: {text!r}")

# Kontrol listesi:
texts = "\n".join(b.text for _, b in doc.iter_blocks())
print("\n=== KAYIP KONTROL ===")
print("  'Header Cell Text' DocIR'de var mi:", "Header Cell Text" in texts, "(<th> - beklenen: False = KAYIP)")
print("  'A caption under the SVG figure' var mi:", "caption under" in texts, "(<figcaption> - beklenen: False = KAYIP)")
print("  cover.png ImageRef'de var mi:", any(i.data for i in page.images) and len(page.images) >= 1)
