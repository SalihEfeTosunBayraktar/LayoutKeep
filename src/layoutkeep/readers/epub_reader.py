"""EPUB reader: turns an EPUB's spine XHTML documents into a DocIR Document.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-epub.md): ebooklib is used ONLY to resolve
OPF metadata, spine order and the manifest (which files are XHTML documents, in what reading
order). The actual XHTML content is parsed and walked with lxml directly from the raw bytes
`ebooklib` read off the zip (never through ebooklib's own HTML parsing helpers, which reparse and
can mangle markup). This keeps `epub_writer.py` able to re-derive the exact same structure from
the same unmodified bytes and make surgical, minimal-diff edits.
"""

from __future__ import annotations

from pathlib import Path

import ebooklib
from ebooklib import epub
from lxml import etree

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    ImageRef,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.readers._epub_css import CssResolver

#: Block-level tags that become a `Block`. Reading order across these tags is tracked via a
#: single global counter (`Block.order`); the per-tag occurrence index is encoded in `Block.id`
#: (e.g. "chap1.xhtml::p#3") so the writer can find the same element again in a fresh parse of
#: the same source file without needing byte offsets carried between the two passes.
BLOCK_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "td",
    # A header cell is a cell. Without it a translated table lost its header row entirely -
    # the words were never in the document, so nothing downstream could miss them.
    "th",
    # The line under a figure is often the only text explaining it, and a caption element
    # is not a paragraph, so the walk stepped straight over it.
    "figcaption",
    "caption",
    # Definition lists: the same argument as list items.
    "dt",
    "dd",
    "pre",
    "code",
}

_BOLD_TAGS = {"b", "strong"}
_ITALIC_TAGS = {"i", "em"}
_MATHML_MATH_TAG = "{http://www.w3.org/1998/Math/MathML}math"

_DUMMY_BBOX = BBox(0.0, 0.0, 0.0, 0.0)

#: Kapsayıcı etiketler: blok çocuğu yoksa paragraf gibi davranır / Container tags treated as blocks when leaf
_CONTAINER_TAGS = {"div", "section", "article", "aside", "main"}


def _localname(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""  # comments, PIs, etc.
    return tag.rsplit("}", 1)[-1].lower()


def _is_leaf_container(el: etree._Element) -> bool:
    # Blok çocuğu olmayan metin taşıyan kapsayıcı mı? / Has text but no block-tag descendants?
    for child in el.iter():
        if child is el:
            continue
        if _localname(child) in BLOCK_TAGS:
            return False
    return bool((el.text and el.text.strip()) or any(
        c.tail and c.tail.strip() for c in el
    ))


def _role_for(tag: str, el: etree._Element) -> BlockRole:
    if tag in ("pre", "code"):
        return BlockRole.CODE
    if any(child.tag == _MATHML_MATH_TAG for child in el.iter()):
        return BlockRole.FORMULA
    if tag == "h1":
        return BlockRole.TITLE
    if tag in ("h2", "h3", "h4", "h5", "h6"):
        return BlockRole.HEADING
    if tag in ("li", "dt", "dd"):
        return BlockRole.LIST
    if tag in ("td", "th"):
        return BlockRole.TABLE
    if tag in ("figcaption", "caption"):
        return BlockRole.CAPTION
    return BlockRole.BODY


def _collect_lines(el: etree._Element, bold: bool, italic: bool, lines: list[list[Span]]) -> None:
    """Depth-first walk collecting text runs as Spans, grouped into Lines split on <br>."""
    tag = _localname(el)
    if tag == "br":
        lines.append([])
        return
    if tag in _BOLD_TAGS:
        bold = True
    elif tag in _ITALIC_TAGS:
        italic = True
    if el.text:
        lines[-1].append(Span(text=el.text, bbox=_DUMMY_BBOX, style=Style(bold=bold, italic=italic)))
    for child in el:
        _collect_lines(child, bold, italic, lines)
        if child.tail:
            lines[-1].append(
                Span(text=child.tail, bbox=_DUMMY_BBOX, style=Style(bold=bold, italic=italic))
            )


def _block_text(lines: list[list[Span]]) -> str:
    return "\n".join("".join(s.text for s in line) for line in lines)


def _walk_blocks(
    el: etree._Element,
    href: str,
    order: list[int],
    tag_counts: dict[str, int],
    out: list[Block],
    resolver=None,
    image_orders: dict[int, int] | None = None,
    image_index: list[int] | None = None,
) -> None:
    tag = _localname(el)

    # A picture's place in the flow is the number of blocks before it. Taken here, while the
    # blocks are being counted - taken afterwards it is larger than all of them, which is how
    # every figure ended up after the last paragraph of its chapter.
    if tag in ("img", "image") and image_orders is not None and image_index is not None:
        image_orders[image_index[0]] = order[0]
        image_index[0] += 1

    if tag in BLOCK_TAGS:
        idx = tag_counts.get(tag, 0)
        tag_counts[tag] = idx + 1
        lines: list[list[Span]] = [[]]
        _collect_lines(el, False, False, lines)
        lines = [ln for ln in lines if ln]
        if lines and _block_text(lines).strip():
            size = 0.0
            align = "left"
            if resolver is not None:
                size, align = resolver.resolve(el)
                for ln in lines:
                    for span in ln:
                        span.style.size = size
            out.append(
                Block(
                    id=f"{href}::{tag}#{idx}",
                    role=_role_for(tag, el),
                    bbox=_DUMMY_BBOX,
                    lines=[Line(spans=ln) for ln in lines],
                    order=order[0],
                    align=align,
                )
            )
            order[0] += 1
        if image_orders is not None and image_index is not None:
            # Block tags are leaves for this walk, so an <img> inside a paragraph is never
            # visited above. It belongs directly after the block that contains it.
            for descendant in el.iter():
                if descendant is not el and _localname(descendant) in ("img", "image"):
                    image_orders[image_index[0]] = order[0]
                    image_index[0] += 1
        return  # block tags are leaves for block detection; don't nest blocks-in-blocks
    # Kapsayıcı etiketler (div, section vb.) blok çocuğu yoksa paragraf gibi davranır
    # Container tags with direct text but no block children act as implicit paragraphs
    if tag in _CONTAINER_TAGS and _is_leaf_container(el):
        idx = tag_counts.get(tag, 0)
        tag_counts[tag] = idx + 1
        lines = [[]]
        _collect_lines(el, False, False, lines)
        lines = [ln for ln in lines if ln]
        if lines and _block_text(lines).strip():
            size = 0.0
            align = "left"
            if resolver is not None:
                size, align = resolver.resolve(el)
                for ln in lines:
                    for span in ln:
                        span.style.size = size
            out.append(
                Block(
                    id=f"{href}::{tag}#{idx}",
                    role=BlockRole.BODY,
                    bbox=_DUMMY_BBOX,
                    lines=[Line(spans=ln) for ln in lines],
                    order=order[0],
                    align=align,
                )
            )
            order[0] += 1
        return
    for child in el:
        _walk_blocks(
            child, href, order, tag_counts, out, resolver, image_orders, image_index
        )


def _walk_images(
    el: etree._Element,
    href: str,
    order: list[int],
    img_idx: list[int],
    out: list[Block],
) -> None:
    """`alt`/`title` on <img> carry translatable text but aren't Blocks in the tag sense, so they
    get synthetic CAPTION blocks whose id encodes which attribute they came from."""
    tag = _localname(el)
    if tag in ("img", "image"):
        idx = img_idx[0]
        img_idx[0] += 1
        for attr, suffix in (("alt", "alt"), ("title", "title")):
            value = el.get(attr)
            if value and value.strip():
                out.append(
                    Block(
                        id=f"{href}::img#{idx}:{suffix}",
                        role=BlockRole.CAPTION,
                        bbox=_DUMMY_BBOX,
                        lines=[Line(spans=[Span(text=value, bbox=_DUMMY_BBOX, style=Style())])],
                        order=order[0],
                    )
                )
                order[0] += 1
        return
    for child in el:
        _walk_images(child, href, order, img_idx, out)


#: An SVG `<image>` names its file with `xlink:href`, or plain `href` in EPUB 3.
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _href_of(el: etree._Element) -> str:
    return el.get(_XLINK_HREF) or el.get("href") or ""


def _extract_page_images(raw: bytes, book, orders: dict[int, int] | None = None) -> list[ImageRef]:
    """Extract the images referenced by one XHTML document as `ImageRef`s.

    The EPUB reader previously ignored every picture (README's "extracts no images"). Keeping
    that while a writer rebuilds the page means figures vanish on EPUB→PDF. Each `<img src>` is
    resolved against the book manifest, its bytes base64-encoded into an ImageRef, so writers
    that rebuild the document (Story-based PDF, DOCX, HTML) can redraw it.

    Bir XHTML dokümanının atıf yaptığı görselleri `ImageRef` listesi olarak çıkarır.
    """
    import base64

    parser = etree.XMLParser(resolve_entities=False, recover=True, huge_tree=True)
    root = etree.fromstring(raw, parser=parser)

    # Resolve every manifest item that is an image, keyed by its href and its basename (some
    # EPUBs reference images from a different path base, so a bare `src="illus.jpg"` resolves).
    image_items: dict[str, object] = {}
    for item in book.get_items():
        mt = getattr(item, "media_type", "") or ""
        if mt.startswith("image/"):
            name = getattr(item, "get_name", lambda: "")()
            image_items[name] = item
            image_items[name.rsplit("/", 1)[-1]] = item

    images: list[ImageRef] = []
    #: Counts every picture element in document order, including any whose file cannot be
    #: resolved, so the numbering matches the walk that recorded where they sit.
    element_index = 0
    for img in root.iter():
        name = _localname(img)
        if name not in ("img", "image"):
            continue
        position = element_index
        element_index += 1
        # EPUB 3 producers wrap a picture in SVG - `<svg><image xlink:href="fig.png"/></svg>` -
        # which carries no `src` at all. Sigil and Calibre both do it, and every such picture
        # was silently absent from the output.
        src = img.get("src") or _href_of(img)
        if not src:
            continue
        item = image_items.get(src) or image_items.get(src.rsplit("/", 1)[-1])
        if item is None:
            continue
        raw_bytes = item.get_content()
        if not raw_bytes:
            continue
        fmt = src.rsplit(".", 1)[-1].lower() if "." in src else "png"
        if fmt == "jpg":
            fmt = "jpeg"
        images.append(
            ImageRef(
                bbox=_DUMMY_BBOX,
                data=base64.b64encode(raw_bytes).decode("ascii"),
                fmt=fmt,
                # Where it sat in the flow, from the same walk that numbered the blocks. An
                # EPUB has no positions, so this is the only thing that keeps a figure with
                # the paragraph it belongs to.
                order=(orders or {}).get(position, -1),
            )
        )
    return images


def _extract_page_blocks(raw: bytes, href: str, resolver=None) -> tuple[list[Block], dict[int, int]]:
    """Parse one XHTML document's raw bytes into Blocks, in document order.

    Re-running this against the same unmodified bytes always produces the same ids and order,
    which is what lets `epub_writer._rewrite_page` re-derive the same structure to locate the
    elements it needs to edit, without either side needing to persist byte offsets.
    """
    parser = etree.XMLParser(resolve_entities=False, recover=True, huge_tree=True)
    root = etree.fromstring(raw, parser=parser)
    order = [0]
    blocks: list[Block] = []
    image_orders: dict[int, int] = {}
    _walk_blocks(root, href, order, {}, blocks, resolver, image_orders, [0])
    _walk_images(root, href, order, [0], blocks)
    return blocks, image_orders


#: Namespaces the package file uses. Both appear verbatim in every EPUB.
_OPF_NS = "http://www.idpf.org/2007/opf"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


def _cover_image(epub_path: Path) -> ImageRef | None:
    """The cover, which is usually declared and never referenced by any page.

    An EPUB names it in the package file - `properties="cover-image"` in EPUB 3, a
    `<meta name="cover">` pointing at a manifest id in EPUB 2 - and many books carry no `<img>`
    for it anywhere. EPUB to EPUB kept it because the archive is copied wholesale; every other
    output is rebuilt from the document, and the document did not have it.

    Read from the archive rather than through ebooklib, which reports `properties` as None and
    returns nothing for the EPUB 2 meta on a book that declares both.
    """
    import base64
    import posixpath
    import zipfile

    parser = etree.XMLParser(resolve_entities=False, recover=True)
    try:
        with zipfile.ZipFile(epub_path) as archive:
            container = etree.fromstring(archive.read("META-INF/container.xml"), parser=parser)
            rootfile = container.find(f".//{{{_CONTAINER_NS}}}rootfile")
            opf_name = rootfile.get("full-path") if rootfile is not None else None
            if not opf_name:
                return None

            package = etree.fromstring(archive.read(opf_name), parser=parser)
            href = _cover_href(package)
            if not href:
                return None

            name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_name), href))
            raw_bytes = archive.read(name)
    except (KeyError, OSError, etree.XMLSyntaxError, zipfile.BadZipFile):
        # A malformed or unusual archive costs the cover, not the conversion.
        return None

    if not raw_bytes:
        return None
    fmt = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
    return ImageRef(
        bbox=_DUMMY_BBOX,
        data=base64.b64encode(raw_bytes).decode("ascii"),
        fmt="jpeg" if fmt == "jpg" else fmt,
    )


def _cover_href(package: etree._Element) -> str:
    """The manifest href of the cover, by either of the two ways a book can declare it."""
    items = {}
    for item in package.iter(f"{{{_OPF_NS}}}item"):
        items[item.get("id") or ""] = item
        if "cover-image" in (item.get("properties") or ""):
            return item.get("href") or ""

    for meta in package.iter(f"{{{_OPF_NS}}}meta"):
        if (meta.get("name") or "").lower() == "cover":
            item = items.get(meta.get("content") or "")
            if item is not None:
                return item.get("href") or ""
    return ""


def read_epub(path: str | Path) -> Document:
    """Read an EPUB file into a DocIR Document. One spine XHTML item becomes one Page."""
    book = epub.read_epub(str(path), options={"ignore_ncx": True})

    doc = Document(source_path=str(path), source_format="epub")
    lang = book.get_metadata("DC", "language")
    if lang:
        doc.source_lang = lang[0][0]

    pages: list[Page] = []
    for page_num, (idref, _linear) in enumerate(book.spine, start=1):
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        href = item.get_name()
        raw = item.get_content()  # raw bytes as stored in the zip, not reparsed by ebooklib
        resolver = CssResolver(raw, book)
        blocks, image_orders = _extract_page_blocks(raw, href, resolver)
        images = _extract_page_images(raw, book, image_orders)
        pages.append(
            Page(
                number=page_num,
                width=0.0,
                height=0.0,
                blocks=blocks,
                images=images,
                source_ref=href,
            )
        )

    # The cover belongs to the first page, and only when that page does not already show it -
    # a cover page with an `<img>` would otherwise carry it twice.
    cover = _cover_image(Path(path))
    if cover is not None and pages:
        already = {page_image.data for page in pages for page_image in page.images}
        if cover.data not in already:
            pages[0].images.insert(0, cover)

    doc.pages = pages
    return doc
