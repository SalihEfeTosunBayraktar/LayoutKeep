"""Tests for epub_writer.write_epub: surgical text-only edits, link/id preservation, lang update."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_epub_fixture import build_sample_epub
from lxml import etree

from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.writers.epub_writer import write_epub


def _read(tmp_path: Path):
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    return src, read_epub(src)


def _page_xhtml(epub_path: Path, name: str) -> bytes:
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(f"OEBPS/{name}")


def test_translating_one_block_only_changes_that_blocks_text(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    heading = next(b for b in chap1.blocks if b.text == "Chapter One")
    from layoutkeep.core.docir import Line, Span

    heading.lines = [Line(spans=[Span(text="Birinci Bölüm", bbox=heading.bbox, style=heading.dominant_style())])]

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    before = _page_xhtml(src, "chap1.xhtml").decode("utf-8")
    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")

    assert "Birinci Bölüm" in after
    assert "Chapter One" not in after
    # everything else in the file is untouched
    assert before.replace("Chapter One", "Birinci Bölüm") == after


def test_href_never_translated_but_alt_and_title_are(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    alt_block = next(b for b in chap1.blocks if b.text == "A cover picture")
    title_block = next(b for b in chap1.blocks if b.text == "Cover")
    from layoutkeep.core.docir import Line, Span

    alt_block.lines = [Line(spans=[Span(text="Kapak resmi", bbox=alt_block.bbox, style=alt_block.dominant_style())])]
    title_block.lines = [Line(spans=[Span(text="Kapak", bbox=title_block.bbox, style=title_block.dominant_style())])]

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")
    assert 'alt="Kapak resmi"' in after
    assert 'title="Kapak"' in after
    assert 'src="images/cover.png"' in after  # src untouched


def test_internal_id_links_still_resolve_after_translation(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    note = next(b for b in chap1.blocks if b.text == "This is the footnote text referenced above.")
    from layoutkeep.core.docir import Line, Span

    note.lines = [Line(spans=[Span(text="Ceviri dipnot metni.", bbox=note.bbox, style=note.dominant_style())])]

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    chap1_out = _page_xhtml(out, "chap1.xhtml")
    chap2_out = _page_xhtml(out, "chap2.xhtml")

    tree1 = etree.fromstring(chap1_out, etree.XMLParser(recover=True))
    ids = {el.get("id") for el in tree1.iter() if el.get("id")}
    assert "note1" in ids  # the target of chap1's own #note1 link still exists

    tree2 = etree.fromstring(chap2_out, etree.XMLParser(recover=True))
    hrefs = {el.get("href") for el in tree2.iter() if el.tag.endswith("}a")}
    assert "chap1.xhtml#note1" in hrefs  # cross-file link untouched


def test_language_updated_in_opf_and_html(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    doc.target_lang = "tr"

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert "<dc:language>tr</dc:language>" in opf

    chap1_out = _page_xhtml(out, "chap1.xhtml").decode("utf-8")
    assert 'lang="tr"' in chap1_out
    assert 'xml:lang="tr"' in chap1_out


def test_no_translation_no_target_lang_is_untouched(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    for name in ("chap1.xhtml", "chap2.xhtml"):
        assert _page_xhtml(src, name) == _page_xhtml(out, name)


def test_translated_block_keeps_original_inline_tag_names(tmp_path: Path) -> None:
    """"This is a <0>bold</0> word and an <1>italic</1> word ..." comes back from a provider with
    its markers intact; docir.apply_segments turns that into multiple spans. The writer must wrap
    them with the SOURCE's own <b>/<i> tag names, not invent <strong>/<em> or flatten to plain text."""
    from layoutkeep.core.docir import apply_segments, segments_from_document

    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    block = next(b for b in chap1.blocks if b.text.startswith("This is a bold word"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    assert seg.source == "This is a <0>bold</0> word and an <1>italic</1> word in a normal sentence."
    seg.target = "Bu bir <0>kalın</0> kelime ve bir <1>italik</1> kelime normal bir cümlede."

    orphans = apply_segments(doc, segments)
    assert orphans == []
    assert not seg.needs_review
    assert len(block.lines[0].spans) == 5  # plain, bold, plain, italic, plain

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)
    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")

    assert "<p>Bu bir <b>kalın</b> kelime ve bir <i>italik</i> kelime normal bir cümlede.</p>" in after
    assert "<strong>" not in after and "<em>" not in after  # never invent a different source tag


def test_translated_block_reuses_strong_not_b(tmp_path: Path) -> None:
    """chap2's block uses <strong>, not <b> - the writer must recover THAT specific tag name."""
    from layoutkeep.core.docir import apply_segments, segments_from_document

    src, doc = _read(tmp_path)
    chap2 = doc.pages[1]
    block = next(b for b in chap2.blocks if b.text.startswith("A quoted paragraph"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    assert seg.source == "A quoted paragraph with <0>strong</0> emphasis."
    seg.target = "Güçlü <0>vurgulu</0> alıntılanmış bir paragraf."

    apply_segments(doc, segments)
    assert len(block.lines[0].spans) > 1

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)
    after = _page_xhtml(out, "chap2.xhtml").decode("utf-8")

    assert "<strong>vurgulu</strong>" in after
    assert "<b>vurgulu</b>" not in after


def test_translated_block_without_inline_styling_stays_plain(tmp_path: Path) -> None:
    """A block with no bold/italic runs must still go through the original plain-text path -
    the inline-tag machinery must not regress the identity-preserving path for the common case."""
    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    heading = next(b for b in chap1.blocks if b.text == "Chapter One")
    from layoutkeep.core.docir import Line, Span

    heading.lines = [Line(spans=[Span(text="Birinci Bölüm", bbox=heading.bbox, style=heading.dominant_style())])]

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")
    assert "<h1 id=\"ch1-title\">Birinci Bölüm</h1>" in after


def test_translation_dropping_markers_falls_back_to_plain_text(tmp_path: Path) -> None:
    """If the provider loses the markers entirely, docir already flags needs_review and collapses
    the block to a single span. The writer must render that as plain text, not crash or leave
    stray marker syntax in the output."""
    from layoutkeep.core.docir import apply_segments, segments_from_document

    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    block = next(b for b in chap1.blocks if b.text.startswith("This is a bold word"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    seg.target = "Bu, normal bir cümlede kalın ve italik bir kelimedir."  # no markers at all

    apply_segments(doc, segments)
    assert seg.needs_review
    assert len(block.lines[0].spans) == 1

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)
    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")

    assert "<p>Bu, normal bir cümlede kalın ve italik bir kelimedir.</p>" in after
    assert "<0>" not in after and "</0>" not in after


def test_broken_markers_stripped_not_leaked_raw(tmp_path: Path) -> None:
    """K2: unusable marker syntax (unknown style index, mismatched close) must be stripped
    before the text is written - `<1>BÖLÜM I.</0>` leaking into the EPUB as-is was observed
    in the real-book e2e run (TOC). The block still flags needs_review (faithful=False), but
    the reader must never see the marker characters."""
    from layoutkeep.core.docir import apply_segments, segments_from_document

    src, doc = _read(tmp_path)
    chap1 = doc.pages[0]
    block = next(b for b in chap1.blocks if b.text.startswith("This is a bold word"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    # style index 9 does not exist (only ~2 inline styles) -> parser returns None
    seg.target = "<9>BÖLÜM I.</9> kalın ve italik bir kelimedir."

    apply_segments(doc, segments)
    assert seg.needs_review  # styling was lost, must be flagged for review
    assert len(block.lines[0].spans) == 1
    plain = block.lines[0].spans[0].text
    assert "<9>" not in plain and "</9>" not in plain  # markers stripped, not leaked

    out = tmp_path / "out.epub"
    write_epub(doc, src, out)
    after = _page_xhtml(out, "chap1.xhtml").decode("utf-8")
    assert "<9>" not in after and "</9>" not in after
    assert "BÖLÜM I." in after
