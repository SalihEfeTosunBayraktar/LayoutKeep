"""DOCX writer: applies a translated DocIR Document back onto the original DOCX file.

Strategy (see docs/CONTRACT.md and docx_reader.py): never rebuild a part through python-docx or
through lxml's serializer. Every zip entry is copied byte-for-byte from the source, except:
  - docProps/core.xml: only the <dc:language> text is replaced (if a target language is set).
  - each part that produced Pages (word/document.xml, headers, footers, footnotes.xml): only the
    text of Blocks whose content actually changed is touched, via surgical edits at the exact
    byte offsets of the <w:t> elements that carry that paragraph's text. Those offsets are found
    by re-walking the SAME unmodified bytes with `docx_reader`'s extraction functions (which are
    deterministic - same input, same ids/order) plus a small regex-based <w:p>/<w:t> locator -
    never by reparsing and reserializing the tree.
  - <w:lang w:val="..."/> attributes are updated to the target language wherever they occur, in
    every part that was touched, when a target language is set.
Everything not explicitly touched - run properties (fonts, rsids, proofing state), numbering,
styles.xml, section properties, bookmarks, hyperlink targets, field codes, images, embedded
objects, comments and tracked changes - is copied through unchanged.

Only <w:t> element text is ever edited. Structure (run count, hyperlink/bookmark wrappers, field
code elements) is never added or removed, which is what keeps ids like footnote references and
internal bookmarks intact across a translation pass.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from lxml import etree

from layoutkeep.core.docir import Block, Document, Page
from layoutkeep.readers.docx_reader import (
    W,
    _extract_footnote_paragraphs,
    _extract_paragraphs,
    _localname,
    _run_style,
)

_BLOCK_ID_RE = re.compile(r"^(?P<part>.+)::p#(?P<idx>\d+)$")

_WP_OPEN_RE = re.compile(r"<w:p(?![a-zA-Z])[^>]*>")
_WP_CLOSE_RE = re.compile(r"</w:p\s*>")
_WT_TAG_RE = re.compile(r"<w:t(?![a-zA-Z])(?P<attrs>[^>]*)>", re.IGNORECASE)
_WT_CLOSE_RE = re.compile(r"</w:t\s*>", re.IGNORECASE)
_LANG_TAG_RE = re.compile(r"<w:lang\b[^>]*/?>", re.IGNORECASE)


def write_docx(doc: Document, src_path: str | Path, out_path: str | Path) -> None:
    src_path = Path(src_path)
    out_path = Path(out_path)

    with zipfile.ZipFile(src_path, "r") as zin:
        names = zin.namelist()
        infos = {info.filename: info for info in zin.infolist()}
        contents = {name: zin.read(name) for name in names}

    if doc.target_lang and "docProps/core.xml" in contents:
        contents["docProps/core.xml"] = _update_core_language(contents["docProps/core.xml"], doc.target_lang)

    href_to_page = {page.source_ref: page for page in doc.pages}
    for part, page in href_to_page.items():
        if part not in contents:
            continue
        is_footnotes = part == "word/footnotes.xml"
        contents[part] = _rewrite_part(contents[part], page, doc.target_lang, is_footnotes)

    _write_zip(out_path, names, contents, infos)


def _write_zip(
    out_path: Path,
    names: list[str],
    contents: dict[str, bytes],
    infos: dict[str, zipfile.ZipInfo],
) -> None:
    with zipfile.ZipFile(out_path, "w") as zout:
        for name in names:
            src_info = infos[name]
            zi = zipfile.ZipInfo(name, date_time=src_info.date_time)
            zi.compress_type = src_info.compress_type
            zi.external_attr = src_info.external_attr
            zout.writestr(zi, contents[name])


def _detect_encoding(raw: bytes) -> str:
    m = re.match(rb"<\?xml[^>]*encoding=[\"']([^\"']+)[\"']", raw)
    return m.group(1).decode("ascii") if m else "utf-8"


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _update_core_language(core_xml: bytes, target_lang: str) -> bytes:
    pattern = re.compile(rb"(<dc:language[^>]*>)([^<]*)(</dc:language>)", re.IGNORECASE)
    if not pattern.search(core_xml):
        return core_xml
    return pattern.sub(lambda m: m.group(1) + target_lang.encode("utf-8") + m.group(3), core_xml)


def _update_lang_attrs(text: str, target_lang: str) -> str:
    """Word records proofing language on <w:lang w:val="..."/> inside run properties. This is the
    DOCX equivalent of EPUB's <html lang> - the only per-part place the language shows up."""

    def repl(m: re.Match[str]) -> str:
        return re.sub(r'w:val="[^"]*"', f'w:val="{target_lang}"', m.group(0))

    return _LANG_TAG_RE.sub(repl, text)


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
# Locating elements in a fresh parse of the unmodified source
# --------------------------------------------------------------------------------------


def _find_p_by_idx(root: etree._Element, target_idx: int) -> etree._Element | None:
    """The idx-th <w:p> in document order, unconditionally - matches docx_reader._walk_paragraphs'
    counting scheme (idx_box increments for every <w:p>, whether or not it becomes a Block)."""
    for counter, el in enumerate(root.iter(f"{W}p")):
        if counter == target_idx:
            return el
    return None


def _find_footnote_p_by_idx(root: etree._Element, target_idx: int) -> etree._Element | None:
    """Mirrors docx_reader._extract_footnote_paragraphs' counting: skip separator footnotes,
    only count direct <w:p> children of real <w:footnote> elements."""
    counter = 0
    for fn in root.iter(f"{W}footnote"):
        if fn.get(f"{W}type") in ("separator", "continuationSeparator"):
            continue
        for p in fn.findall(f"{W}p"):
            if counter == target_idx:
                return p
            counter += 1
    return None


def _raw_p_index(root: etree._Element, target_el: etree._Element) -> int:
    """Position of `target_el` among ALL <w:p> elements in the tree, in document order. This is
    the index the raw-text <w:p> scanner (`_iter_wp_spans`) uses, which is independent of which
    part-specific counting scheme (footnote-aware or not) picked `target_el` in the first place."""
    for i, el in enumerate(root.iter(f"{W}p")):
        if el is target_el:
            return i
    return -1


def _iter_wp_spans(text: str) -> Iterator[tuple[int, int]]:
    """Yield (inner_start, inner_end) for each <w:p>...</w:p> region, in document order.
    <w:p> never nests, so unlike EPUB's tag matcher this needs no depth tracking."""
    pos = 0
    while True:
        m_open = _WP_OPEN_RE.search(text, pos)
        if not m_open:
            return
        if m_open.group(0).rstrip().endswith("/>"):
            pos = m_open.end()
            continue
        m_close = _WP_CLOSE_RE.search(text, m_open.end())
        if not m_close:
            return
        yield m_open.end(), m_close.start()
        pos = m_close.end()


def _iter_wt_slots(text: str) -> list[dict]:
    """Every non-empty <w:t>...</w:t> region within `text`, in document order. Self-closing and
    empty <w:t> elements are skipped - they never became a Span at read time (docx_reader only
    appends a Span `if el.text:`), so there is nothing here for a translation to land on."""
    slots = []
    pos = 0
    while True:
        m = _WT_TAG_RE.search(text, pos)
        if not m:
            return slots
        attrs = m.group("attrs")
        if attrs.rstrip().endswith("/"):
            pos = m.end()
            continue
        close = _WT_CLOSE_RE.search(text, m.end())
        if not close:
            return slots
        inner_start, inner_end = m.end(), close.start()
        if inner_start == inner_end:
            pos = close.end()
            continue
        slots.append(
            {
                "open_end": m.end(),
                "inner_start": inner_start,
                "inner_end": inner_end,
                "has_preserve": "xml:space=" in attrs,
            }
        )
        pos = close.end()
    return slots


def _style_of_t(t_el: etree._Element) -> tuple[bool, bool]:
    node = t_el.getparent()
    while node is not None and _localname(node) != "r":
        node = node.getparent()
    if node is None:
        return False, False
    return _run_style(node)


def _style_slots_for_p(p_text: str, target_el: etree._Element) -> list[tuple[tuple[bool, bool], dict]] | None:
    """Pair each non-empty <w:t> in `target_el` (lxml, gives style) with its byte offsets in
    `p_text` (raw source, gives position) by zipping the two in document order. Returns None if
    the counts disagree - malformed source or an assumption this reader/writer pair doesn't
    model - so the caller can fall back to a plain-text edit instead of guessing."""
    wt_els = [t for t in target_el.iter(f"{W}t") if t.text]
    slots = _iter_wt_slots(p_text)
    if len(wt_els) != len(slots):
        return None
    return [(_style_of_t(t), slot) for t, slot in zip(wt_els, slots, strict=False)]


def _group_slots(
    styled_slots: list[tuple[tuple[bool, bool], dict]],
) -> list[tuple[tuple[bool, bool], list[dict]]]:
    """Group consecutive slots that share a (bold, italic) key - the same grouping docir.py's
    `_inline_styles`/`_block_runs` implicitly rely on via the reader's own run-merging."""
    groups: list[tuple[tuple[bool, bool], list[dict]]] = []
    for key, slot in styled_slots:
        if groups and groups[-1][0] == key:
            groups[-1][1].append(slot)
        else:
            groups.append((key, [slot]))
    return groups


def _fill_slots(p_start: int, slots: list[dict], new_text: str) -> list[tuple[int, int, str]]:
    """Put `new_text` into the first slot, clear the rest. Consolidating onto one <w:t> instead of
    trying to preserve the original run split is deliberate: Word's run boundaries mostly don't
    correspond to anything meaningful once the sentence has been retranslated."""
    if not slots:
        return []
    edits: list[tuple[int, int, str]] = []
    first = slots[0]
    escaped = _escape_text(new_text)
    edits.append((p_start + first["inner_start"], p_start + first["inner_end"], escaped))
    if escaped and not first["has_preserve"]:
        # Leading/trailing whitespace in the translation must not be silently trimmed by Word's
        # renderer - xml:space="preserve" is the hint that stops that.
        edits.append((p_start + first["open_end"] - 1, p_start + first["open_end"] - 1, ' xml:space="preserve"'))
    for slot in slots[1:]:
        if slot["inner_start"] != slot["inner_end"]:
            edits.append((p_start + slot["inner_start"], p_start + slot["inner_end"], ""))
    return edits


def _paragraph_edits(
    text: str, p_range: tuple[int, int], block: Block, target_el: etree._Element
) -> list[tuple[int, int, str]]:
    p_start, p_end = p_range
    p_text = text[p_start:p_end]
    spans = block.lines[0].spans if block.lines else []

    styled = _style_slots_for_p(p_text, target_el)
    if not styled:
        slots = _iter_wt_slots(p_text)
        return _fill_slots(p_start, slots, block.text)

    groups = _group_slots(styled)
    if len(spans) <= 1:
        flat_slots = [slot for _, group_slots in groups for slot in group_slots]
        return _fill_slots(p_start, flat_slots, block.text)

    # Multiple differently-styled spans came back from translation (docir's <N>...</N> markers) -
    # distribute them across the original style groups in order, matching by (bold, italic).
    by_key: dict[tuple[bool, bool], list[int]] = {}
    for gi, (key, _) in enumerate(groups):
        by_key.setdefault(key, []).append(gi)
    dominant = block.dominant_style()
    dominant_key = (dominant.bold, dominant.italic)
    cursor: dict[tuple[bool, bool], int] = {}
    assigned: dict[int, str] = dict.fromkeys(range(len(groups)), "")
    for span in spans:
        key = (span.style.bold, span.style.italic)
        candidates = by_key.get(key) or by_key.get(dominant_key) or [0]
        pos = cursor.get(key, 0)
        gi = candidates[pos] if pos < len(candidates) else candidates[-1]
        cursor[key] = pos + 1
        assigned[gi] += span.text

    edits: list[tuple[int, int, str]] = []
    for gi, (_key, group_slots) in enumerate(groups):
        edits.extend(_fill_slots(p_start, group_slots, assigned[gi]))
    return edits


def _rewrite_part(raw: bytes, page: Page, target_lang: str | None, is_footnotes: bool) -> bytes:
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding)
    part = page.source_ref

    if is_footnotes:
        fresh_by_id = {b.id: b for b in _extract_footnote_paragraphs(raw, part)}
    else:
        fresh_by_id = {b.id: b for b in _extract_paragraphs(raw, part, None)}

    edits: list[tuple[int, int, str]] = []
    tree: etree._Element | None = None

    def get_tree() -> etree._Element:
        nonlocal tree
        if tree is None:
            parser = etree.XMLParser(resolve_entities=False, huge_tree=True)
            tree = etree.fromstring(raw, parser=parser)
        return tree

    wp_cache: dict[int, tuple[int, int]] = {}
    wp_gen = None
    wp_position = 0

    def wp_span(idx: int) -> tuple[int, int] | None:
        nonlocal wp_gen, wp_position
        if idx in wp_cache:
            return wp_cache[idx]
        if wp_gen is None:
            wp_gen = _iter_wp_spans(text)
        while wp_position <= idx:
            try:
                span = next(wp_gen)
            except StopIteration:
                break
            wp_cache[wp_position] = span
            wp_position += 1
        return wp_cache.get(idx)

    for block in page.blocks_in_reading_order():
        fresh = fresh_by_id.get(block.id)
        if fresh is None or fresh.text == block.text:
            continue  # untouched: leave the original bytes exactly as they are
        m = _BLOCK_ID_RE.match(block.id)
        if not m:
            raise ValueError(f"unrecognised block id from docx_reader: {block.id!r}")
        idx = int(m["idx"])

        root = get_tree()
        target_el = _find_footnote_p_by_idx(root, idx) if is_footnotes else _find_p_by_idx(root, idx)
        if target_el is None:
            continue
        raw_idx = _raw_p_index(root, target_el)
        p_range = wp_span(raw_idx)
        if p_range is None:
            continue
        edits.extend(_paragraph_edits(text, p_range, block, target_el))

    text = _apply_edits(text, edits)
    if target_lang:
        text = _update_lang_attrs(text, target_lang)
    return text.encode(encoding)
