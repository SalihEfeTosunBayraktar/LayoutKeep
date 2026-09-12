"""Build a realistic multi-page DOCX report to demonstrate the DOCX -> PNG conversion.

Hand-built with zipfile, in the style of `tests/fixtures/build_docx_fixture.py`, but with real
prose instead of a handful of test lines: a title page, several sections of body text, a
bulleted list, a table of results, bold/italic emphasis, a running header and footer, and a
footnote - the shape of document that made docx->png lose a third of its words before the OCR
detector was fixed to crop sparse pages before recognizing them (see docs/ENGINE-ARCHITECTURE.md).

Written here rather than taken from anywhere, so the repository can publish it and the demo
built from it without a licence question. The content is invented; any resemblance to a real
test programme is coincidental.

    .venv/Scripts/python.exe tools/make_sample_docx_report.py docs/samples/battery_test_report.docx
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

DOCUMENT_RELS = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>
"""

CORE_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Battery Cycle Life Test - Summary Report</dc:title>
<dc:creator>LayoutKeep sample</dc:creator>
<dc:language>en-US</dc:language>
</cp:coreProperties>
"""

APP_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>LayoutKeep</Application></Properties>
"""

STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="22"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:i/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/></w:style>
<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>
"""

NUMBERING_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:abstractNum w:abstractNumId="0">
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="-"/></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
"""

HEADER1_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:p><w:r><w:t>Battery Cycle Life Test - Summary Report</w:t></w:r></w:p>
</w:hdr>
"""

FOOTER1_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:p><w:r><w:t xml:space="preserve">LayoutKeep sample document - not a real test programme</w:t></w:r></w:p>
</w:ftr>
"""

FOOTNOTES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>
<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>
<w:footnote w:id="1">
<w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>
<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>
<w:r><w:t xml:space="preserve"> Ambient temperature held at 23C +/- 2C for the duration of the test programme.</w:t></w:r>
</w:p>
</w:footnote>
</w:footnotes>
"""


def _p(text: str, *, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{style_xml}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def _list_item(text: str) -> str:
    return (
        '<w:p><w:pPr><w:pStyle w:val="ListParagraph"/>'
        '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    width = 9000 // len(headers)
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for _ in headers)

    def cell(text: str, *, bold: bool = False) -> str:
        run_props = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return (
            f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
            f'<w:p><w:r>{run_props}<w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:tc>'
        )

    header_row = "<w:tr>" + "".join(cell(h, bold=True) for h in headers) + "</w:tr>"
    body_rows = "".join(
        "<w:tr>" + "".join(cell(c) for c in row) + "</w:tr>" for row in rows
    )
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        "</w:tblBorders></w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>{header_row}{body_rows}</w:tbl>"
    )


def _emph(before: str, bold_word: str, middle: str, italic_word: str, after: str) -> str:
    return (
        "<w:p>"
        f'<w:r><w:t xml:space="preserve">{before}</w:t></w:r>'
        f'<w:r><w:rPr><w:b/></w:rPr><w:t>{bold_word}</w:t></w:r>'
        f'<w:r><w:t xml:space="preserve">{middle}</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>{italic_word}</w:t></w:r>'
        f'<w:r><w:t xml:space="preserve">{after}</w:t></w:r>'
        "</w:p>"
    )


BODY_PARAGRAPHS = [
    _p("Battery Cycle Life Test", style="Title"),
    _p("Summary report for the 18650 cell qualification programme", style="Subtitle"),
    _p("1. Purpose", style="Heading1"),
    _p(
        "This report summarises the cycle life results collected for the candidate 18650 "
        "lithium-ion cell across three charge rates. The programme's aim was to establish "
        "whether the cell retains at least 80 percent of its rated capacity after 500 full "
        "charge-discharge cycles, the threshold this product line requires before a supplier "
        "is qualified for volume orders."
    ),
    _p("2. Method", style="Heading1"),
    _p(
        "Twelve cells were drawn at random from a single production lot and divided into three "
        "groups of four, one group per charge rate: 0.5C, 1.0C and 1.5C. Each cell was cycled "
        "between 3.0V and 4.2V at 23C in a temperature-controlled chamber, with a full "
        "capacity check performed every 50 cycles on a calibrated cycler."
    ),
    _emph(
        "Cells that fell outside ",
        "2 percent",
        " of the group's mean capacity at the first check were flagged and continued on a ",
        "separate log",
        ", so a single early outlier would not distort the reported group average.",
    ),
    _p("Two cells were withdrawn from the programme before the 500-cycle mark: one for a "
       "connector fault unrelated to the cell itself, and one for a thermal excursion that "
       "exceeded the test's safety envelope. Neither withdrawal is included in the averages "
       "below."),
    _p("3. Results", style="Heading1"),
    _p("Table 1 lists the capacity retention measured at the 500-cycle checkpoint for each "
       "group, averaged across the surviving cells in that group."),
    _table(
        ["Charge rate", "Cells", "Capacity retention", "Notes"],
        [
            ["0.5C", "4", "86.4%", "Within spec"],
            ["1.0C", "3", "83.1%", "Within spec"],
            ["1.5C", "3", "76.8%", "Below 80% threshold"],
        ],
    ),
    _p("The 1.5C group is the only one that falls short of the qualification threshold. Its "
       "degradation curve was noticeably steeper after cycle 300, which is consistent with "
       "accelerated lithium plating at the higher charge rate rather than a gradual, linear "
       "fade."),
    _p("4. Observations", style="Heading1"),
    _list_item("Internal resistance rose by roughly 40 percent across all three groups over "
               "the course of the programme, with the steepest rise in the 1.5C group."),
    _list_item("No swelling or venting was observed on any cell at teardown."),
    _list_item("Capacity fade was closely linear for the 0.5C and 1.0C groups; the 1.5C group "
               "showed the knee described above."),
    _p("5. Conclusion", style="Heading1"),
    _p(
        "The candidate cell meets the 80 percent retention threshold at both 0.5C and 1.0C "
        "charge rates but not at 1.5C. If the product's charging profile can be capped at 1.0C "
        "in the field, this cell is recommended for qualification. If 1.5C fast charging is a "
        "requirement, a different cell or a revised charge algorithm should be evaluated "
        "before this supplier is approved for that use case."
    ),
    _p(
        "This has a footnote about test conditions"
        "<FOOTNOTE_MARKER/>."
    ),
]


def _paragraphs_xml() -> str:
    out = []
    for para in BODY_PARAGRAPHS:
        if "<FOOTNOTE_MARKER/>" in para:
            before, after = para.split("<FOOTNOTE_MARKER/>")
            out.append(
                before
                + '<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr>'
                '<w:footnoteReference w:id="1"/></w:r>'
                + after
            )
        else:
            out.append(para)
    return "".join(out)


DOCUMENT_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>
{paragraphs}
<w:sectPr>
<w:headerReference w:type="default" r:id="rId4"/>
<w:footerReference w:type="default" r:id="rId5"/>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
</w:sectPr>
</w:body>
</w:document>
"""


def build_battery_report(path: str | Path) -> None:
    document_xml = DOCUMENT_XML_TEMPLATE.format(paragraphs=_paragraphs_xml()).encode("utf-8")
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in (
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", RELS),
            ("docProps/core.xml", CORE_XML),
            ("docProps/app.xml", APP_XML),
            ("word/document.xml", document_xml),
            ("word/_rels/document.xml.rels", DOCUMENT_RELS),
            ("word/styles.xml", STYLES_XML),
            ("word/numbering.xml", NUMBERING_XML),
            ("word/footnotes.xml", FOOTNOTES_XML),
            ("word/header1.xml", HEADER1_XML),
            ("word/footer1.xml", FOOTER1_XML),
        ):
            zf.writestr(zipfile.ZipInfo(name), data, zipfile.ZIP_DEFLATED)


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/samples/battery_test_report.docx")
    target.parent.mkdir(parents=True, exist_ok=True)
    build_battery_report(target)
    print(f"{target} written ({target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
