"""Minimal CSS resolution for EPUB: font size and text alignment per element.

EPUB XHTML carries its typography in `<style>` blocks and linked stylesheets, but
`epub_reader` walks only markup. Without resolving those declarations, every block lands in
DocIR with `Style.size == 0.0` and `Block.align == "left"`, so a cross-format export that
rebuilds the document (EPUB→PDF, EPUB→DOCX, EPUB→HTML) flattens headings to body size and
centres nothing.

This is deliberately NOT a CSS engine: no cascade specificity scoring, no media queries, no
`@import` chase. It resolves the two properties that matter for layout fidelity — `font-size`
and `text-align` — by matching element tag/class/id against a simple rule table, with inline
`style` winning over stylesheet rules. `em`/`%` sizes resolve against a fixed base; that covers
the overwhelming majority of real EPUBs (Project Gutenberg included) and leaves exotic cases on
the honest default rather than guessing.
"""

from __future__ import annotations

import re

from lxml import etree

#: Base body font size in points when nothing else declares one.
_BASE_SIZE = 12.0

#: HTML-ish tag defaults in points, used when no rule applies (browser-compatible ratios).
_TAG_DEFAULT_SIZE = {
    "h1": 24.0, "h2": 18.0, "h3": 16.0, "h4": 14.0, "h5": 12.0, "h6": 10.0,
    "p": 12.0, "li": 12.0, "td": 11.0, "th": 11.0, "blockquote": 11.0,
    "pre": 11.0, "code": 11.0,
}

_FONT_SIZE = re.compile(r"font-size\s*:\s*([0-9.]+)\s*(em|rem|px|pt|%)?", re.IGNORECASE)
_TEXT_ALIGN = re.compile(r"text-align\s*:\s*(left|center|right|justify)\b", re.IGNORECASE)

#: px → pt. 1 px ≈ 0.75 pt at 96 dpi.
_PX_TO_PT = 0.75


def _localname(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _parse_declarations(text: str) -> tuple[float | None, str | None]:
    """Return `(size_pt, align)` from a `declarations` block, `None` for the absent ones."""
    size: float | None = None
    size_m = _FONT_SIZE.search(text)
    if size_m:
        value = float(size_m.group(1))
        unit = (size_m.group(2) or "pt").lower()
        if unit in ("em", "rem"):
            size = value * _BASE_SIZE
        elif unit == "px":
            size = value * _PX_TO_PT
        elif unit == "%":
            size = value / 100.0 * _BASE_SIZE
        else:  # pt, or a bare number treated as pt
            size = value
    align_m = _TEXT_ALIGN.search(text)
    align = align_m.group(1).lower() if align_m else None
    return size, align


class _Rule:
    """One stylesheet rule: a simple selector and the two properties we care about."""

    __slots__ = ("align", "classes", "element_id", "size", "tag")

    def __init__(self, selector: str, size: float | None, align: str | None) -> None:
        self.tag = ""
        self.classes: list[str] = []
        self.element_id = ""
        # Drop pseudo-classes / combinators / children; match the final simple part.
        simple = re.split(r"[:>+~\[\s]", selector.strip(), maxsplit=1)[0]
        if " " in simple:
            simple = simple.rsplit(" ", 1)[-1]
        for part in re.findall(r"[.#]?[a-zA-Z_][\w-]*", simple):
            if part.startswith("#"):
                self.element_id = part[1:].lower()
            elif part.startswith("."):
                self.classes.append(part[1:].lower())
            elif not self.tag:
                self.tag = part.lower()
        self.size = size
        self.align = align

    def matches(self, tag: str, classes: list[str], element_id: str) -> bool:
        if self.element_id and self.element_id != element_id:
            return False
        if self.tag and self.tag != tag:
            return False
        return not self.classes or set(self.classes).issubset(classes)


def _collect_rules(book) -> list[_Rule]:
    """Stylesheet rules from every linked CSS item in the book."""
    rules: list[_Rule] = []
    for item in book.get_items():
        if getattr(item, "media_type", "") == "text/css":
            try:
                css = item.get_content().decode("utf-8", "replace")
            except (UnicodeDecodeError, AttributeError):
                continue
            for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
                for selector in match.group(1).split(","):
                    selector = selector.strip()
                    if not selector:
                        continue
                    size, align = _parse_declarations(match.group(2))
                    if size is not None or align is not None:
                        rules.append(_Rule(selector, size, align))
    return rules


class CssResolver:
    """Resolve `font-size` and `text-align` for the elements of one XHTML document."""

    def __init__(self, raw_xhtml: bytes, book) -> None:
        self._rules = _collect_rules(book)
        parser = etree.XMLParser(resolve_entities=False, recover=True, huge_tree=True)
        self._root = etree.fromstring(raw_xhtml, parser=parser)
        # Inline <style> blocks in this very file join the rule table.
        for style_el in self._root.iter():
            if _localname(style_el) == "style":
                text = "".join(style_el.itertext())
                for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
                    for selector in match.group(1).split(","):
                        selector = selector.strip()
                        if not selector:
                            continue
                        size, align = _parse_declarations(match.group(2))
                        if size is not None or align is not None:
                            self._rules.append(_Rule(selector, size, align))

    def resolve(self, el: etree._Element) -> tuple[float, str]:
        """Return `(size_pt, align)` for a single element, inline style winning."""
        size, align = _parse_declarations(el.get("style") or "")
        if size is None or align is None:
            tag = _localname(el)
            classes = [c.lower() for c in (el.get("class") or "").split() if c]
            element_id = (el.get("id") or "").lower()
            for rule in self._rules:
                if rule.matches(tag, classes, element_id):
                    if size is None and rule.size is not None:
                        size = rule.size
                    if align is None and rule.align is not None:
                        align = rule.align
                    if size is not None and align is not None:
                        break
        if size is None:
            size = _TAG_DEFAULT_SIZE.get(_localname(el), _BASE_SIZE)
        return size, align or "left"
