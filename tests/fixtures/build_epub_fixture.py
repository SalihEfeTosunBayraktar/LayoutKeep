"""Builds a small, reproducible EPUB2 fixture used by the epub reader/writer tests.

Deliberately hand-built with zipfile rather than ebooklib, so the test controls the exact bytes
(mimetype first & stored, entity usage, self-closing style) that the identity round trip is
checked against.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

CONTAINER_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

CONTENT_OPF = b"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:12345678-1234-1234-1234-123456789012</dc:identifier>
    <dc:title>Sample Book</dc:title>
    <dc:language>en</dc:language>
    <dc:creator>Test Author</dc:creator>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap2" href="chap2.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="img1" href="images/cover.png" media-type="image/png"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chap1"/>
    <itemref idref="chap2"/>
  </spine>
</package>
"""

TOC_NCX = b"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:12345678-1234-1234-1234-123456789012"/>
  </head>
  <docTitle><text>Sample Book</text></docTitle>
  <navMap>
    <navPoint id="navpoint-1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="chap1.xhtml"/>
    </navPoint>
    <navPoint id="navpoint-2" playOrder="2">
      <navLabel><text>Chapter 2</text></navLabel>
      <content src="chap2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""

STYLE_CSS = b"""body { font-family: serif; }
p.note { color: #333; }
"""

CHAP1_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head><title>Chapter 1</title><link href="style.css" rel="stylesheet" type="text/css"/></head>
<body>
<h1 id="ch1-title">Chapter One</h1>
<p>This is a <b>bold</b> word and an <i>italic</i> word in a normal sentence.</p>
<p class="note">See the note<a href="#note1">[1]</a> below for details.</p>
<ul>
<li>First item</li>
<li>Second item</li>
</ul>
<p><img src="images/cover.png" alt="A cover picture" title="Cover"/></p>
<pre>def add(a, b):
    return a + b
</pre>
<p id="note1">This is the footnote text referenced above.</p>
</body>
</html>
"""

CHAP2_XHTML = b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head><title>Chapter 2</title><link href="style.css" rel="stylesheet" type="text/css"/></head>
<body>
<h2>Chapter Two</h2>
<blockquote><p>A quoted paragraph with <strong>strong</strong> emphasis.</p></blockquote>
<table>
<tr><td>Row one, cell one</td><td>Row one, cell two</td></tr>
</table>
<p>See <a href="chap1.xhtml#note1">the footnote</a> in chapter one.</p>
<code>x = 1</code>
</body>
</html>
"""

# 1x1 transparent PNG, arbitrary binary content whose bytes just need to survive untouched.
COVER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844440000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000155274db3000000"
    "0049454e44ae426082"
)


def build_sample_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", zipfile.ZIP_STORED)
        for name, data in (
            (_CONTAINER_NAME, CONTAINER_XML),
            ("OEBPS/content.opf", CONTENT_OPF),
            ("OEBPS/toc.ncx", TOC_NCX),
            ("OEBPS/style.css", STYLE_CSS),
            ("OEBPS/chap1.xhtml", CHAP1_XHTML),
            ("OEBPS/chap2.xhtml", CHAP2_XHTML),
            ("OEBPS/images/cover.png", COVER_PNG),
        ):
            zf.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED)


_CONTAINER_NAME = "META-INF/container.xml"
