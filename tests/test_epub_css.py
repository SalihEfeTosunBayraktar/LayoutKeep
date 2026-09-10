"""Tests for EPUB CSS resolution (font-size, text-align) in readers/_epub_css.py."""

from __future__ import annotations

from lxml import etree

from layoutkeep.readers._epub_css import CssResolver, _parse_declarations


def _el(xml: str) -> etree._Element:
    return etree.fromstring(xml)


def _resolver(raw_xhtml: bytes, css_items: list[bytes]) -> CssResolver:
    class _Item:
        def __init__(self, media_type: str, content: bytes) -> None:
            self.media_type = media_type
            self._content = content

        def get_content(self) -> bytes:
            return self._content

    class _Book:
        def __init__(self, items: list[_Item]) -> None:
            self._items = items

        def get_items(self):
            return self._items

    return CssResolver(raw_xhtml, _Book([_Item("text/css", c) for c in css_items]))


def test_parse_declarations_pt_and_align() -> None:
    size, align = _parse_declarations("font-size: 14pt; text-align: center;")
    assert size == 14.0
    assert align == "center"


def test_parse_declarations_em_and_px() -> None:
    size, _ = _parse_declarations("font-size: 1.5em;")
    assert size == 18.0  # 1.5 * 12 base
    size, _ = _parse_declarations("font-size: 16px;")
    assert size == 12.0  # 16 * 0.75


def test_parse_declarations_percent() -> None:
    size, _ = _parse_declarations("font-size: 150%;")
    assert size == 18.0  # 1.5 * 12 base


def test_inline_style_wins_over_stylesheet() -> None:
    r = _resolver(
        b'<html><body><p style="font-size: 20pt; text-align: right;">x</p></body></html>',
        [b"p { font-size: 10pt; text-align: left; }"],
    )
    p = next(e for e in r._root.iter() if e.tag.endswith("p"))
    size, align = r.resolve(p)
    assert size == 20.0
    assert align == "right"


def test_stylesheet_rule_by_class() -> None:
    r = _resolver(
        b'<html><body><p class="note">x</p><p>y</p></body></html>',
        [b"p.note { font-size: 16pt; text-align: center; }"],
    )
    note = next(e for e in r._root.iter() if e.get("class") == "note")
    plain = next(e for e in r._root.iter() if e.tag.endswith("p") and not e.get("class"))
    assert r.resolve(note) == (16.0, "center")
    # plain paragraph falls back to the p tag default (12pt, left)
    assert r.resolve(plain) == (12.0, "left")


def test_tag_default_sizes() -> None:
    r = _resolver(b"<html><body><h1>a</h1><h2>b</h2><h3>c</h3></body></html>", [])
    h1 = next(e for e in r._root.iter() if e.tag.endswith("h1"))
    h2 = next(e for e in r._root.iter() if e.tag.endswith("h2"))
    h3 = next(e for e in r._root.iter() if e.tag.endswith("h3"))
    assert r.resolve(h1)[0] == 24.0
    assert r.resolve(h2)[0] == 18.0
    assert r.resolve(h3)[0] == 16.0


def test_rule_with_id_and_pseudo_stripped() -> None:
    r = _resolver(
        b'<html><body><h2 id="ch2">Chapter</h2></body></html>',
        [b"h2#ch2 { font-size: 22pt; } h2:hover { font-size: 99pt; }"],
    )
    h2 = next(e for e in r._root.iter() if e.tag.endswith("h2"))
    assert r.resolve(h2)[0] == 22.0
