"""EPUB writer: applies a translated DocIR Document back onto the original EPUB file.

Strategy (see docs/CONTRACT.md and .claude/agents/lk-epub.md): never re-serialize the EPUB
through ebooklib and never fully reparse+reserialize an XHTML document through lxml either, since
both round trips are known to rewrite `&nbsp;`, self-closing tags and the XML declaration. Instead
every zip entry is copied byte-for-byte from the source, except:
  - content.opf: only the <dc:language> text is replaced (if a target language is set).
  - each spine XHTML page: only the text of Blocks whose content actually changed is replaced, via
    a surgical string edit at the exact byte offsets of that element/attribute. Those offsets are
    found by re-walking the SAME unmodified source bytes with `epub_reader._extract_page_blocks`
    (deterministic: same input always yields the same block ids/order) plus a small regex-based
    tag matcher — never by fully reparsing and reserializing the tree. Recovering which inline
    tag (<b> vs <strong>, <i> vs <em>) a translated bold/italic run should reuse also re-walks
    the same unmodified bytes, this time with lxml (read-only, never written back as a tree).
Everything not explicitly touched -- tag structure, class names, ids, other attributes, CSS,
images, toc.ncx/nav.xhtml -- is copied through unchanged.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import ebooklib
from ebooklib import epub
from lxml import etree

from layoutkeep.core.docir import Block, Document, Page, Span
from layoutkeep.readers.epub_reader import (
    _BOLD_TAGS,
    _ITALIC_TAGS,
    BLOCK_TAGS,
    _extract_page_blocks,
    _localname,
)

_CONTAINER_PATH = "META-INF/container.xml"

#: Matches the ids epub_reader.py assigns: "{href}::{tag}#{idx}" or "{href}::img#{idx}:{suffix}".
_BLOCK_ID_RE = re.compile(r"^(?P<href>.+)::(?P<tag>[a-zA-Z0-9]+)#(?P<idx>\d+)(?::(?P<suffix>alt|title))?$")


def write_epub(doc: Document, src_path: str | Path, out_path: str | Path) -> None:
    src_path = Path(src_path)
    out_path = Path(out_path)

    with zipfile.ZipFile(src_path, "r") as zin:
        names = zin.namelist()
        infos = {info.filename: info for info in zin.infolist()}
        contents = {name: zin.read(name) for name in names}

    opf_path = _find_opf_path(contents[_CONTAINER_PATH])
    if doc.target_lang:
        contents[opf_path] = _update_opf_language(contents[opf_path], doc.target_lang)

    # ebooklib used ONLY to resolve which files are spine XHTML documents and their hrefs -
    # never to parse or re-emit their content.
    book = epub.read_epub(str(src_path), options={"ignore_ncx": True})
    href_to_page = {page.source_ref: page for page in doc.pages}
    opf_dir = posixpath.dirname(opf_path)

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        href = item.get_name()  # matches Page.source_ref, relative to the OPF's directory
        page = href_to_page.get(href)
        if page is None:
            continue
        zip_path = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
        if zip_path not in contents:
            continue
        contents[zip_path] = _rewrite_page(contents[zip_path], page, doc.target_lang)

    _write_zip(out_path, names, contents, infos)


def _write_zip(
    out_path: Path,
    names: list[str],
    contents: dict[str, bytes],
    infos: dict[str, zipfile.ZipInfo],
) -> None:
    ordered = names
    if "mimetype" in ordered:
        ordered = ["mimetype"] + [n for n in ordered if n != "mimetype"]
    with zipfile.ZipFile(out_path, "w") as zout:
        for name in ordered:
            data = contents[name]
            if name == "mimetype":
                zout.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_STORED)
                continue
            src_info = infos[name]
            zi = zipfile.ZipInfo(name, date_time=src_info.date_time)
            zi.compress_type = src_info.compress_type
            zi.external_attr = src_info.external_attr
            zout.writestr(zi, data)


def _find_opf_path(container_xml: bytes) -> str:
    m = re.search(rb'full-path="([^"]+)"', container_xml)
    if not m:
        raise ValueError("could not find OPF path in META-INF/container.xml")
    return m.group(1).decode("utf-8")


def _update_opf_language(opf: bytes, target_lang: str) -> bytes:
    pattern = re.compile(rb"(<dc:language[^>]*>)([^<]*)(</dc:language>)", re.IGNORECASE)
    return pattern.sub(lambda m: m.group(1) + target_lang.encode("utf-8") + m.group(3), opf)


def _detect_encoding(raw: bytes) -> str:
    m = re.match(rb"<\?xml[^>]*encoding=[\"']([^\"']+)[\"']", raw)
    return m.group(1).decode("ascii") if m else "utf-8"


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape_text(text).replace('"', "&quot;")


def _iter_tag_spans(text: str, tag: str) -> Iterator[tuple[int, int, int]]:
    """Yield (inner_start, inner_end, next_pos) for each <tag ...>...</tag> region, in document
    order, correctly skipping past nested same-name tags (e.g. nested <blockquote>)."""
    open_re = re.compile(rf"<{tag}(?=[\s>/])[^>]*>", re.IGNORECASE)
    close_re = re.compile(rf"</{tag}\s*>", re.IGNORECASE)
    pos = 0
    while True:
        m_open = open_re.search(text, pos)
        if not m_open:
            return
        if m_open.group(0).rstrip().endswith("/>"):
            pos = m_open.end()
            continue
        depth = 1
        scan = m_open.end()
        inner_start = scan
        while depth > 0:
            m_next = open_re.search(text, scan)
            m_close = close_re.search(text, scan)
            if not m_close:
                return  # malformed source; bail out rather than guess
            if m_next and m_next.start() < m_close.start() and not m_next.group(0).rstrip().endswith("/>"):
                depth += 1
                scan = m_next.end()
            else:
                depth -= 1
                scan = m_close.end()
        inner_end = m_close.start()
        yield inner_start, inner_end, scan
        pos = scan


def _iter_img_tags(text: str) -> Iterator[tuple[int, int]]:
    tag_re = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE)
    pos = 0
    while True:
        m = tag_re.search(text, pos)
        if not m:
            return
        yield m.start(), m.end()
        pos = m.end()


def _attr_value_span(text: str, tag_start: int, tag_end: int, attr: str) -> tuple[int, int] | None:
    m = re.search(rf'{attr}\s*=\s*"([^"]*)"', text[tag_start:tag_end], re.IGNORECASE)
    if not m:
        return None
    return tag_start + m.start(1), tag_start + m.end(1)


def _update_html_lang(text: str, target_lang: str) -> str:
    def repl(m: re.Match[str]) -> str:
        tag = m.group(0)
        tag = re.sub(r'\blang="[^"]*"', f'lang="{target_lang}"', tag)
        return re.sub(r'\bxml:lang="[^"]*"', f'xml:lang="{target_lang}"', tag)

    return re.sub(r"<html\b[^>]*>", repl, text, count=1, flags=re.IGNORECASE)


def _apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    if not edits:
        return text
    ordered = sorted(edits, key=lambda e: e[0])
    out: list[str] = []
    cursor = 0
    for start, end, new in ordered:
        out.append(text[cursor:start])
        out.append(new)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


# --------------------------------------------------------------------------------------
# Inline styling on write-back
#
# docir.apply_segments() can turn a translated block into MULTIPLE spans (bold/italic runs
# carried through via <0>...</0> markers - see docir._replace_block_text). Style only records
# bold/italic booleans, not which source tag produced them, so <b> vs <strong> and <i> vs <em>
# can't be recovered from the Span alone. Instead we re-walk the ORIGINAL source element (the
# same technique _rewrite_page already uses to locate edit offsets) and record, for each
# (bold, italic) combination that actually occurs, the first source tag name that produced it.
# That map is then reused to wrap the translated spans, so a source <strong> is written back as
# <strong>, never invented as <b>.
# --------------------------------------------------------------------------------------

_DEFAULT_BOLD_TAG = "b"
_DEFAULT_ITALIC_TAG = "i"

# (bold_tag_name_or_None, italic_tag_name_or_None) for a given (bold, italic) style pair.
_TagMap = dict[tuple[bool, bool], tuple[str | None, str | None]]


def _find_block_element(root: etree._Element, tag: str, idx: int) -> etree._Element | None:
    """Find the idx-th occurrence of `tag`, using the exact same leaf-pruning walk as
    epub_reader._walk_blocks, so the occurrence count matches the ids epub_reader assigns."""
    counter = 0
    for el in root.iter():
        t = _localname(el)
        if t not in BLOCK_TAGS:
            continue
        # Mirror _walk_blocks: block tags are leaves, so a block tag nested inside another block
        # tag (which epub_reader never descends into) must not be counted here either. lxml's
        # root.iter() would otherwise still find it, since it doesn't know about the pruning.
        ancestor = el.getparent()
        nested = False
        while ancestor is not None:
            if _localname(ancestor) in BLOCK_TAGS:
                nested = True
                break
            ancestor = ancestor.getparent()
        if nested:
            continue
        if t == tag:
            if counter == idx:
                return el
            counter += 1
    return None


def _collect_tagged_runs(
    el: etree._Element,
    bold_tag: str | None,
    italic_tag: str | None,
    runs: list[tuple[str, str | None, str | None]],
) -> None:
    """Depth-first walk mirroring epub_reader._collect_lines, but recording the tag name that
    turned bold/italic on instead of just a boolean."""
    tag = _localname(el)
    if tag in _BOLD_TAGS:
        bold_tag = tag
    elif tag in _ITALIC_TAGS:
        italic_tag = tag
    if el.text:
        runs.append((el.text, bold_tag, italic_tag))
    for child in el:
        _collect_tagged_runs(child, bold_tag, italic_tag, runs)
        if child.tail:
            runs.append((child.tail, bold_tag, italic_tag))


def _source_tag_map(root: etree._Element, tag: str, idx: int) -> _TagMap:
    """Map (bold, italic) -> original (bold_tag, italic_tag) for one block element, keyed by
    first occurrence. Empty if the element can't be located (e.g. malformed source) - callers
    then fall back to default tag names."""
    el = _find_block_element(root, tag, idx)
    if el is None:
        return {}
    runs: list[tuple[str, str | None, str | None]] = []
    _collect_tagged_runs(el, None, None, runs)
    tag_map: _TagMap = {}
    for _text, bold_tag, italic_tag in runs:
        key = (bold_tag is not None, italic_tag is not None)
        tag_map.setdefault(key, (bold_tag, italic_tag))
    return tag_map


def _render_inline_html(spans: list[Span], dominant_key: tuple[bool, bool], tag_map: _TagMap) -> str:
    """Render translated spans as inline-tagged HTML, reusing the original tag names recovered
    in `tag_map`. Bold wraps outside italic when a run has both - Style doesn't record which was
    the outer tag in the source, so this is a fixed, documented choice rather than a guess."""
    out: list[str] = []
    for span in spans:
        text = _escape_text(span.text)
        if not text:
            continue
        key = (span.style.bold, span.style.italic)
        if key == dominant_key:
            out.append(text)
            continue
        bold_tag, italic_tag = tag_map.get(key, (None, None))
        if key[0] and not bold_tag:
            bold_tag = _DEFAULT_BOLD_TAG
        if key[1] and not italic_tag:
            italic_tag = _DEFAULT_ITALIC_TAG
        if italic_tag:
            text = f"<{italic_tag}>{text}</{italic_tag}>"
        if bold_tag:
            text = f"<{bold_tag}>{text}</{bold_tag}>"
        out.append(text)
    return "".join(out)


def _block_replacement_html(block: Block, source_root: etree._Element, tag: str, idx: int) -> str:
    """The HTML to put where `block`'s old text was: plain escaped text unless the translation
    kept multiple differently-styled spans, in which case inline tags are rebuilt around them."""
    spans = block.lines[0].spans if block.lines else []
    if len(spans) <= 1:
        # No inline styling to carry, or apply_segments() lost the markers and already flagged
        # needs_review - either way the existing plain-text path is correct and must not regress.
        return _escape_text(block.text)
    dominant = block.dominant_style()
    dominant_key = (dominant.bold, dominant.italic)
    tag_map = _source_tag_map(source_root, tag, idx)
    return _render_inline_html(spans, dominant_key, tag_map)


def _rewrite_page(raw: bytes, page: Page, target_lang: str | None) -> bytes:
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding)

    fresh_blocks, _image_orders = _extract_page_blocks(raw, page.source_ref)
    fresh_by_id = {b.id: b for b in fresh_blocks}

    edits: list[tuple[int, int, str]] = []
    source_root: etree._Element | None = None

    def get_source_root() -> etree._Element:
        nonlocal source_root
        if source_root is None:
            parser = etree.XMLParser(resolve_entities=False, recover=True, huge_tree=True)
            source_root = etree.fromstring(raw, parser=parser)
        return source_root

    # Per-tag occurrence -> span, filled in lazily and cached so that two blocks sharing the same
    # (tag, idx) - e.g. an <img>'s alt and title - both resolve to the same element without either
    # one consuming the other's position in the underlying generator.
    tag_caches: dict[str, dict[int, tuple[int, int]]] = {}
    tag_gens: dict[str, Iterator[tuple[int, int, int]]] = {}
    tag_positions: dict[str, int] = {}
    img_cache: dict[int, tuple[int, int]] = {}
    img_gen: Iterator[tuple[int, int]] | None = None
    img_position = 0

    def tag_span(tag: str, idx: int) -> tuple[int, int] | None:
        cache = tag_caches.setdefault(tag, {})
        if idx in cache:
            return cache[idx]
        gen = tag_gens.setdefault(tag, _iter_tag_spans(text, tag))
        pos = tag_positions.get(tag, 0)
        while pos <= idx:
            try:
                inner_start, inner_end, _next_pos = next(gen)
            except StopIteration:
                break
            cache[pos] = (inner_start, inner_end)
            pos += 1
        tag_positions[tag] = pos
        return cache.get(idx)

    def img_span(idx: int) -> tuple[int, int] | None:
        nonlocal img_gen, img_position
        if idx in img_cache:
            return img_cache[idx]
        if img_gen is None:
            img_gen = _iter_img_tags(text)
        while img_position <= idx:
            try:
                span = next(img_gen)
            except StopIteration:
                break
            img_cache[img_position] = span
            img_position += 1
        return img_cache.get(idx)

    for block in page.blocks_in_reading_order():
        fresh = fresh_by_id.get(block.id)
        if fresh is None or fresh.text == block.text:
            continue  # untouched: leave the original bytes exactly as they are
        m = _BLOCK_ID_RE.match(block.id)
        if not m:
            raise ValueError(f"unrecognised block id from epub_reader: {block.id!r}")
        tag, idx, suffix = m["tag"], int(m["idx"]), m["suffix"]

        if suffix:  # img alt/title -> attribute edit
            span = img_span(idx)
            if span:
                attr_span = _attr_value_span(text, span[0], span[1], suffix)
                if attr_span:
                    edits.append((attr_span[0], attr_span[1], _escape_attr(block.text)))
            continue

        target = tag_span(tag, idx)
        if target:
            html = _block_replacement_html(block, get_source_root(), tag, idx)
            edits.append((target[0], target[1], html))

    text = _apply_edits(text, edits)
    if target_lang:
        text = _update_html_lang(text, target_lang)
    return text.encode(encoding)
