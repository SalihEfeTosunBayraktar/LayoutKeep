"""Rich fixtures for the real-translation verification runs: documents that carry
pictures, charts and tables, not just prose.

The existing fixtures were built to test readers and writers in isolation, and the
format matrix's own sources carry no images on the PDF and DOCX side (sample_report.pdf
has zero, build_sample_docx has zero). A "lossless" claim that was never measured
against a document with figures in it is not a claim.

Everything is built with the same libraries the other fixtures use (pymupdf, zipfile,
PIL), so no new dependency is added and the documents stay reproducible.

    .venv/Scripts/python.exe tests/fixtures/build_rich_fixture.py
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

PAGE_W, PAGE_H = 400.0, 500.0


# --------------------------------------------------------------------------------------
# Raster pieces shared by the PDF, DOCX and EPUB builders
# --------------------------------------------------------------------------------------


def chart_png(w: int = 220, h: int = 140) -> bytes:
    """A bar 'chart' as a PNG: 5 bars, axes, no text (labels stay in document text)."""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline="#0f172a", width=2)  # frame
    base_y = h - 18
    d.line((14, 8, 14, base_y), fill="#0f172a", width=2)  # y axis
    d.line((14, base_y, w - 8, base_y), fill="#0f172a", width=2)  # x axis
    heights = [42, 78, 58, 96, 66]
    x = 26
    for bh in heights:
        d.rectangle((x, base_y - bh, x + 26, base_y), fill="#2563eb")
        x += 34
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def logo_png(w: int = 48, h: int = 48) -> bytes:
    """A small 'logo' PNG: a blue square with a white L."""
    img = Image.new("RGB", (w, h), "#2563eb")
    d = ImageDraw.Draw(img)
    d.line((10, 8, 10, h - 8), fill="white", width=6)
    d.line((10, h - 10, w - 8, h - 10), fill="white", width=6)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def photo_like_png(w: int = 160, h: int = 100) -> bytes:
    """A 'photo' PNG: gradient ground with two shapes, like a figure screenshot."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        shade = int(240 - (y / h) * 70)
        d.line((0, y, w, y), fill=(shade, shade, min(255, shade + 10)))
    d.ellipse((18, 22, 66, 70), outline="#0f172a", width=3)
    d.polygon([(90, 70), (120, 24), (150, 70)], outline="#dc2626", width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# PDF: two pages - prose+table+logo, chart+photo+caption
# --------------------------------------------------------------------------------------


def build_rich_pdf(path: Path) -> None:
    doc = pymupdf.open()

    # -- page 1: title, bold/italic paragraph, a table, a logo raster -------------------
    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    p1.insert_text((40, 50), "Quarterly Field Report", fontsize=16, fontname="hebo")
    p1.insert_text((40, 70), "Prepared by the measurement team", fontsize=9, fontname="heit")

    p1.insert_text((40, 100), "This word is ", fontsize=11, fontname="helv")
    x = 40 + pymupdf.get_text_length("This word is ", fontname="helv", fontsize=11)
    p1.insert_text((x, 100), "bold", fontsize=11, fontname="hebo")
    x += pymupdf.get_text_length("bold", fontname="hebo", fontsize=11)
    p1.insert_text((x, 100), " and this is ", fontsize=11, fontname="helv")
    x += pymupdf.get_text_length(" and this is ", fontname="helv", fontsize=11)
    p1.insert_text((x, 100), "italic", fontsize=11, fontname="heit")

    p1.insert_image(pymupdf.Rect(300, 30, 348, 78), stream=logo_png())
    p1.insert_textbox(
        pymupdf.Rect(40, 120, 360, 150),
        "The table below lists the three battery cells used in the test campaign.",
        fontsize=11, fontname="helv",
    )

    # a real vector table
    cols = [40, 130, 220, 310]
    rows = [170, 192, 214, 236, 258]
    for r in rows:
        p1.draw_line(pymupdf.Point(cols[0], r), pymupdf.Point(cols[-1] + 40, r))
    for c in cols:
        p1.draw_line(pymupdf.Point(c, rows[0]), pymupdf.Point(c, rows[-1]))
    table_text = [
        ["Cell", "Cycle", "Capacity", "Status"],
        ["A-101", "500", "92 percent", "Pass"],
        ["A-102", "800", "88 percent", "Pass"],
        ["A-103", "1200", "71 percent", "Review"],
    ]
    for ri, row in enumerate(table_text):
        for ci, cell in enumerate(row):
            fontname = "hebo" if ri == 0 else "helv"
            p1.insert_text((cols[ci] + 4, rows[ri] + 16), cell, fontsize=9, fontname=fontname)

    p1.insert_textbox(
        pymupdf.Rect(40, 290, 360, 420),
        "The chart on the next page summarises the discharge curves for the three cells. "
        "All values were recorded at 25 degrees with a 0.5 C discharge rate, and the review "
        "flag on A-103 is explained in section 4 of this report.",
        fontsize=11, fontname="helv",
    )

    # -- page 2: chart raster, photo, captions -----------------------------------------
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    p2.insert_text((40, 45), "Figure 1: discharge summary", fontsize=12, fontname="hebo")
    p2.insert_image(pymupdf.Rect(40, 60, 260, 150), stream=chart_png())
    p2.insert_textbox(
        pymupdf.Rect(40, 160, 260, 185),
        "Figure 1: capacity retained after 500, 800 and 1200 cycles.",
        fontsize=8, fontname="helv",
    )
    p2.insert_image(pymupdf.Rect(270, 60, 370, 122), stream=photo_like_png())
    p2.insert_textbox(
        pymupdf.Rect(270, 130, 380, 155),
        "Test bench with the three cells mounted.",
        fontsize=8, fontname="helv",
    )
    p2.insert_textbox(
        pymupdf.Rect(40, 220, 360, 340),
        "Reading the chart: the blue bars show the retained capacity share per cell. "
        "Cell A-103 lost 29 percent of its rated capacity by cycle 1200, which sits at "
        "the review threshold defined before the campaign started.",
        fontsize=11, fontname="helv",
    )

    doc.save(str(path))
    doc.close()


# --------------------------------------------------------------------------------------
# DOCX: body with an inline picture, bold/italic runs, a table, a list
# --------------------------------------------------------------------------------------

_CT = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_CORE = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Rich Field Report</dc:title><dc:creator>Test Author</dc:creator>
</cp:coreProperties>"""

_STYLES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/></w:style>
</w:styles>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""

# 12700 EMU per point: 180x140pt inline chart drawing
_DRAWING = """<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<wp:inline distT="0" distB="0" distL="0" distR="0" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:docPr id="1" name="Chart 1"/>
<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:nvPicPr><pic:cNvPr id="1" name="Chart 1"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="rId7" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"""

_DOCUMENT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>
<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Rich Field Report</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>1. Test Campaign</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">The </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>measurement</w:t></w:r><w:r><w:t xml:space="preserve"> team ran three cells for </w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>1200 cycles</w:t></w:r><w:r><w:t xml:space="preserve"> at 25 degrees.</w:t></w:r></w:p>
<w:p><w:r><w:t>The chart below summarises the retained capacity per cell.</w:t></w:r></w:p>
<w:p><w:r>{_DRAWING.format(cx=12700 * 180, cy=12700 * 110)}</w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Figure 1: capacity retained after the campaign. </w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>Cell A-103 sits at the review threshold.</w:t></w:r></w:p>
<w:tbl>
<w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>
<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>
<w:tr><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Cell</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Cycles</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Capacity</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>A-101</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>500</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>92 percent</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>A-102</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>800</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>88 percent</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>A-103</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>1200</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p><w:r><w:t>71 percent</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
<w:p><w:r><w:t>Conclusion: two cells passed, one is flagged for review.</w:t></w:r></w:p>
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>
</w:body></w:document>"""


def build_rich_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("[Content_Types].xml"), _CT, zipfile.ZIP_DEFLATED)
        zf.writestr(zipfile.ZipInfo("_rels/.rels"), _RELS, zipfile.ZIP_DEFLATED)
        zf.writestr(zipfile.ZipInfo("docProps/core.xml"), _CORE, zipfile.ZIP_DEFLATED)
        zf.writestr(zipfile.ZipInfo("word/document.xml"), _DOCUMENT.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr(
            zipfile.ZipInfo("word/_rels/document.xml.rels"), _DOC_RELS.encode(), zipfile.ZIP_DEFLATED
        )
        zf.writestr(zipfile.ZipInfo("word/styles.xml"), _STYLES, zipfile.ZIP_DEFLATED)
        zf.writestr(zipfile.ZipInfo("word/media/image1.png"), chart_png(), zipfile.ZIP_DEFLATED)


# --------------------------------------------------------------------------------------
# PNG: a chart with OCR-readable labels baked into the pixels
# --------------------------------------------------------------------------------------


def build_rich_png(path: Path) -> None:
    """A one-page 'scanned figure' PNG: chart graphic + text labels around it."""
    w, h = 1200, 800
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    # title text (drawn big enough for OCR)
    d.text((60, 40), "Quarterly Field Report - Figure 1", fill="#0f172a")

    # chart frame + bars
    base_y, x0 = 640, 160
    d.line((x0, 120, x0, base_y), fill="#0f172a", width=4)
    d.line((x0, base_y, 1080, base_y), fill="#0f172a", width=4)
    bars = [("A-101", 500, 92), ("A-102", 800, 88), ("A-103", 1200, 71)]
    x = x0 + 60
    for label, cycles, cap in bars:
        bh = int(cap * 4.4)
        d.rectangle((x, base_y - bh, x + 180, base_y), fill="#2563eb")
        d.text((x + 30, base_y + 18), f"{label} / {cycles}", fill="#0f172a")
        x += 280
    d.text((60, 90), "capacity retained after the cycle campaign", fill="#334155")

    img.save(path, format="PNG", dpi=(150, 150))


if __name__ == "__main__":
    out = Path(__file__).parent
    build_rich_pdf(out / "rich_report.pdf")
    build_rich_docx(out / "rich_report.docx")
    build_rich_png(out / "rich_report.png")
    print(f"built: rich_report.pdf, rich_report.docx, rich_report.png in {out}")
