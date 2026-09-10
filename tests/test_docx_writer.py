"""Tests for docx_writer.write_docx: surgical <w:t>-only edits, run-property preservation, and
language updates."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_docx_fixture import build_sample_docx

from layoutkeep.core.docir import Line, Span, apply_segments, segments_from_document
from layoutkeep.readers.docx_reader import read_docx
from layoutkeep.writers.docx_writer import write_docx


def _read(tmp_path: Path):
    src = tmp_path / "sample.docx"
    build_sample_docx(src)
    return src, read_docx(src)


def _part(docx_path: Path, name: str) -> str:
    with zipfile.ZipFile(docx_path) as zf:
        return zf.read(name).decode("utf-8")


def test_translating_title_only_changes_that_paragraph(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    body = doc.pages[0]
    title = next(b for b in body.blocks if b.text == "Sample Document Title")
    title.lines = [Line(spans=[Span(text="Örnek Belge Başlığı", bbox=title.bbox, style=title.dominant_style())])]

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    before = _part(src, "word/document.xml")
    after = _part(out, "word/document.xml")

    assert "Örnek Belge Başlığı" in after
    assert "Sample Document Title" not in after
    # every other paragraph in the part is untouched
    assert "Section One" in after
    assert before.count("<w:p>") + before.count("<w:p ") == after.count("<w:p>") + after.count("<w:p ")


def test_table_cell_translation(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    body = doc.pages[0]
    cell = next(b for b in body.blocks if b.text == "Row one, cell one")
    cell.lines = [Line(spans=[Span(text="Birinci satır, birinci hücre", bbox=cell.bbox, style=cell.dominant_style())])]

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    after = _part(out, "word/document.xml")
    assert "Birinci satır, birinci hücre" in after
    assert "Row one, cell two" in after  # the other cell is untouched


def test_list_item_translation(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    body = doc.pages[0]
    item = next(b for b in body.blocks if b.text == "First item")
    item.lines = [Line(spans=[Span(text="İlk öğe", bbox=item.bbox, style=item.dominant_style())])]

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    after = _part(out, "word/document.xml")
    assert "İlk öğe" in after
    assert "Second item" in after
    # numbering reference on the translated paragraph survives untouched
    assert '<w:numId w:val="1"/>' in after


def test_header_and_footer_translation(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    header = next(p for p in doc.pages if p.source_ref == "word/header1.xml")
    footer = next(p for p in doc.pages if p.source_ref == "word/footer1.xml")
    hb = header.blocks[0]
    hb.lines = [Line(spans=[Span(text="Çalışan Üstbilgi", bbox=hb.bbox, style=hb.dominant_style())])]
    fb = footer.blocks[0]
    fb.lines = [Line(spans=[Span(text="Altbilgi metni", bbox=fb.bbox, style=fb.dominant_style())])]

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    assert "Çalışan Üstbilgi" in _part(out, "word/header1.xml")
    assert "Altbilgi metni" in _part(out, "word/footer1.xml")


def test_footnote_translation_keeps_footnote_reference_mark(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    footnotes = next(p for p in doc.pages if p.source_ref == "word/footnotes.xml")
    fb = next(b for b in footnotes.blocks if "footnote text" in b.text)
    fb.lines = [Line(spans=[Span(text=" Bu, dipnot metnidir.", bbox=fb.bbox, style=fb.dominant_style())])]

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    after = _part(out, "word/footnotes.xml")
    assert "Bu, dipnot metnidir." in after
    assert "<w:footnoteRef/>" in after  # the reference mark run is untouched structurally


def test_language_updated_in_core_and_runs(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    doc.target_lang = "tr-TR"

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    core = _part(out, "docProps/core.xml")
    assert "<dc:language>tr-TR</dc:language>" in core

    document = _part(out, "word/document.xml")
    assert 'w:val="tr-TR"' in document  # w:lang inherited from docDefaults... document.xml has none
    # docDefaults lives in styles.xml, which is out of DocIR's Page scope and stays untouched
    styles = _part(out, "word/styles.xml")
    assert 'w:val="en-US"' in styles


def test_translated_inline_bold_italic_preserves_run_properties(tmp_path: Path) -> None:
    """The paragraph's <w:rPr> for the bold/italic runs must survive untouched - only the <w:t>
    text inside each run changes."""
    src, doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if b.text.startswith("This is a bold word"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    assert seg.source == "This is a <0>bold</0> word and an <1>italic</1> word."
    seg.target = "Bu bir <0>kalın</0> kelime ve bir <1>italik</1> kelime."

    orphans = apply_segments(doc, segments)
    assert orphans == []
    assert not seg.needs_review
    assert len(block.lines[0].spans) == 5

    before = _part(src, "word/document.xml")
    out = tmp_path / "out.docx"
    write_docx(doc, src, out)
    after = _part(out, "word/document.xml")

    print("BEFORE paragraph:\n", before[before.index("This is a") - 5 : before.index("</w:p>", before.index("This is a")) + 6])
    print("AFTER paragraph:\n", after[after.index("Bu bir") - 5 : after.index("</w:p>", after.index("Bu bir")) + 6])

    assert "<w:rPr><w:b/></w:rPr>" in after
    assert "<w:rPr><w:i/></w:rPr>" in after
    assert "kalın" in after and "italik" in after
    assert "<0>" not in after and "</0>" not in after


def test_translation_dropping_markers_falls_back_to_single_run(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    body = doc.pages[0]
    block = next(b for b in body.blocks if b.text.startswith("This is a bold word"))

    segments = segments_from_document(doc)
    seg = next(s for s in segments if s.block_id == block.id)
    seg.target = "Kalın ve italik kelimeler içeren normal bir cümle."  # no markers

    apply_segments(doc, segments)
    assert seg.needs_review
    assert len(block.lines[0].spans) == 1

    out = tmp_path / "out.docx"
    write_docx(doc, src, out)
    after = _part(out, "word/document.xml")

    assert "Kalın ve italik kelimeler içeren normal bir cümle." in after
    assert "<0>" not in after


def test_no_translation_no_target_lang_document_part_untouched(tmp_path: Path) -> None:
    src, doc = _read(tmp_path)
    out = tmp_path / "out.docx"
    write_docx(doc, src, out)
    assert _part(src, "word/document.xml") == _part(out, "word/document.xml")
