"""DOCX reader: turns a Word document's XML parts into a DocIR Document.

Strategy (see docs/CONTRACT.md and the EPUB agent's precedent in epub_reader.py):
`python-docx` is deliberately NOT used. It re-serializes `document.xml` through its own object
model on save, which drops or reorders rsids, proofing state and anything it doesn't model -
exactly the class of damage the EPUB agent found with ebooklib. `docx_writer.py` needs the exact
same raw bytes this reader parsed in order to make surgical, minimal-diff edits, so this reader
works directly off the zip entries via `zipfile` + `lxml`, and never asks a library to rebuild the
XML for us.

One `<w:p>` (paragraph) is one `Block`. There is no native "page" in a DOCX (pagination is a
layout-engine concern DOCX doesn't record), so each XML *part* that carries visible text becomes
one `Page`: the main body (`word/document.xml`), each header/footer, and the footnotes part.
`Page.source_ref` carries the part name, which `docx_writer.py` uses to find its way back.

A block's id encodes exactly how to re-find it in a fresh parse of the same unmodified bytes:
"{part}::p#{idx}", where idx is the 0-based occurrence count of <w:p> within that part's counting
scope (unconditional for document/header/footer, footnote-type-aware for footnotes.xml). This
mirrors epub_reader's "{href}::{tag}#{idx}" scheme so the writer can relocate elements without
either side persisting byte offsets between reader and writer runs.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_DUMMY_BBOX = BBox(0.0, 0.0, 0.0, 0.0)

#: Elements whose text content is never part of the visible, translatable flow.
_SKIP_TAGS = {"instrText", "delText", "rPr", "pPr", "bookmarkStart", "bookmarkEnd"}

_HEADER_RE = re.compile(r"^word/header\d+\.xml$")
_FOOTER_RE = re.compile(r"^word/footer\d+\.xml$")

#: Footnote types that carry no user content (the separator glyphs Word draws above footnotes).
_NON_CONTENT_FOOTNOTE_TYPES = {"separator", "continuationSeparator"}


def _localname(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _flag(rPr: etree._Element | None, name: str) -> bool:
    if rPr is None:
        return False
    el = rPr.find(f"{W}{name}")
    if el is None:
        return False
    val = el.get(f"{W}val")
    if val is None:
        return True
    return val.lower() not in ("0", "false", "off")


def _run_style(r_el: etree._Element) -> tuple[bool, bool]:
    rPr = r_el.find(f"{W}rPr")
    return _flag(rPr, "b"), _flag(rPr, "i")


def _collect_run_text(el: etree._Element, bold: bool, italic: bool, lines: list[list[Span]]) -> None:
    """Depth-first walk collecting <w:t> text as Spans, grouped into Lines split on <w:br>/<w:cr>.

    Field codes (<w:instrText>), tracked-change deletions (<w:delText>) and bookmarks carry no
    <w:t> and are skipped by construction - only elements this function explicitly recognises
    contribute text.
    """
    tag = _localname(el)
    if tag in _SKIP_TAGS:
        return
    if tag == "r":
        bold, italic = _run_style(el)
    if tag == "t":
        if el.text:
            lines[-1].append(Span(text=el.text, bbox=_DUMMY_BBOX, style=Style(bold=bold, italic=italic)))
        return
    if tag == "tab":
        lines[-1].append(Span(text="\t", bbox=_DUMMY_BBOX, style=Style(bold=bold, italic=italic)))
        return
    if tag in ("br", "cr"):
        lines.append([])
        return
    for child in el:
        _collect_run_text(child, bold, italic, lines)


def _merge_line(spans: list[Span]) -> list[Span]:
    """Merge adjacent same-style spans. Word splits sentences across runs for reasons (rsids,
    spellcheck state) unrelated to formatting; without merging, every such split becomes its own
    marker pair when the block is later sent for translation."""
    merged: list[Span] = []
    for s in spans:
        if merged and merged[-1].style.key() == s.style.key():
            merged[-1].text += s.text
        else:
            merged.append(Span(text=s.text, bbox=s.bbox, style=s.style, direction=s.direction))
    return merged


def _paragraph_lines(p_el: etree._Element) -> list[Line]:
    lines: list[list[Span]] = [[]]
    for child in p_el:
        if _localname(child) == "pPr":
            continue
        _collect_run_text(child, False, False, lines)
    return [Line(spans=_merge_line(ln)) for ln in lines if ln]


def _in_table_cell(p_el: etree._Element) -> bool:
    node = p_el.getparent()
    while node is not None:
        if _localname(node) == "tc":
            return True
        node = node.getparent()
    return False


def _role_for_paragraph(p_el: etree._Element, forced_role: BlockRole | None) -> BlockRole:
    if forced_role is not None:
        return forced_role
    pPr = p_el.find(f"{W}pPr")
    style_val = ""
    numpr = None
    if pPr is not None:
        st = pPr.find(f"{W}pStyle")
        style_val = (st.get(f"{W}val") if st is not None else "") or ""
        numpr = pPr.find(f"{W}numPr")
    sv = style_val.lower()
    if "title" in sv:
        return BlockRole.TITLE
    if sv.startswith("heading"):
        return BlockRole.HEADING
    if "caption" in sv:
        return BlockRole.CAPTION
    if numpr is not None or "list" in sv:
        return BlockRole.LIST
    if _in_table_cell(p_el):
        return BlockRole.TABLE
    return BlockRole.BODY


def _walk_paragraphs(
    el: etree._Element,
    part: str,
    order: list[int],
    idx_box: list[int],
    out: list[Block],
    forced_role: BlockRole | None,
) -> None:
    if _localname(el) == "p":
        idx = idx_box[0]
        idx_box[0] += 1
        lines = _paragraph_lines(el)
        text = "\n".join(line.text for line in lines)
        if lines and text.strip():
            out.append(
                Block(
                    id=f"{part}::p#{idx}",
                    role=_role_for_paragraph(el, forced_role),
                    bbox=_DUMMY_BBOX,
                    lines=lines,
                    order=order[0],
                )
            )
            order[0] += 1
        return
    for child in el:
        _walk_paragraphs(child, part, order, idx_box, out, forced_role)


def _parse(raw: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, huge_tree=True)
    return etree.fromstring(raw, parser=parser)


def _extract_paragraphs(raw: bytes, part: str, forced_role: BlockRole | None) -> list[Block]:
    """Parse one part's raw bytes into Blocks, in document order.

    Re-running this against the same unmodified bytes always produces the same ids/order, which
    is what lets docx_writer relocate the elements it needs to edit without persisted offsets.
    """
    root = _parse(raw)
    order = [0]
    idx_box = [0]
    blocks: list[Block] = []
    _walk_paragraphs(root, part, order, idx_box, blocks, forced_role)
    return blocks


def _extract_footnote_paragraphs(raw: bytes, part: str) -> list[Block]:
    """Like `_extract_paragraphs`, but skips the separator/continuationSeparator pseudo-footnotes
    Word emits (no user content) and only walks real <w:footnote> elements' direct <w:p> children."""
    root = _parse(raw)
    order = [0]
    idx_box = [0]
    blocks: list[Block] = []
    for fn in root.iter(f"{W}footnote"):
        if fn.get(f"{W}type") in _NON_CONTENT_FOOTNOTE_TYPES:
            continue
        for p in fn.findall(f"{W}p"):
            _walk_paragraphs(p, part, order, idx_box, blocks, BlockRole.FOOTNOTE)
    return blocks


def read_docx(path: str | Path) -> Document:
    """Read a DOCX file into a DocIR Document.

    Page layout: DOCX has no native page boundaries, so each XML part carrying visible text
    becomes one Page - the body, each header/footer, and the footnotes part - rather than
    guessing at pagination. `Page.source_ref` is the zip entry name, which the writer uses to
    find the same part again.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        contents = {name: zf.read(name) for name in names}

    doc = Document(source_path=str(path), source_format="docx")
    core = contents.get("docProps/core.xml")
    if core:
        m = re.search(rb"<dc:language[^>]*>([^<]*)</dc:language>", core)
        if m and m.group(1):
            doc.source_lang = m.group(1).decode("utf-8")

    pages: list[Page] = []
    page_num = 1

    if "word/document.xml" in contents:
        blocks = _extract_paragraphs(contents["word/document.xml"], "word/document.xml", None)
        pages.append(Page(number=page_num, width=0.0, height=0.0, blocks=blocks, source_ref="word/document.xml"))
        page_num += 1

    for name in sorted(names):
        forced_role = None
        if _HEADER_RE.match(name):
            forced_role = BlockRole.HEADER
        elif _FOOTER_RE.match(name):
            forced_role = BlockRole.FOOTER
        else:
            continue
        blocks = _extract_paragraphs(contents[name], name, forced_role)
        pages.append(Page(number=page_num, width=0.0, height=0.0, blocks=blocks, source_ref=name))
        page_num += 1

    if "word/footnotes.xml" in contents:
        blocks = _extract_footnote_paragraphs(contents["word/footnotes.xml"], "word/footnotes.xml")
        pages.append(Page(number=page_num, width=0.0, height=0.0, blocks=blocks, source_ref="word/footnotes.xml"))
        page_num += 1

    doc.pages = pages
    return doc
