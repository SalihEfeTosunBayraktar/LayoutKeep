"""Tests for cross-format conversion via layoutkeep.writers.converter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_docx_fixture import build_sample_docx
from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.writers.converter import read_any_document, write_any_document


def test_epub_to_html_conversion(tmp_path: Path) -> None:
    src_epub = tmp_path / "sample.epub"
    build_sample_epub(src_epub)

    doc = read_any_document(src_epub)
    out_html = tmp_path / "sample.html"
    write_any_document(doc, src_epub, out_html)

    assert out_html.exists()
    content = out_html.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert len(content) > 100


def test_read_any_document_missing_file_raises_clear_error(tmp_path: Path) -> None:
    # K3: eksik girdi traceback degil, tek cumlelik FileNotFoundError verir
    missing = tmp_path / "yok.epub"
    with pytest.raises(FileNotFoundError) as excinfo:
        read_any_document(missing)
    assert "bulunamadı" in str(excinfo.value) or "not found" in str(excinfo.value)


def test_read_any_document_directory_raises_clear_error(tmp_path: Path) -> None:
    # K3: klasor yolu dosya gibi verilirse net hata
    with pytest.raises(FileNotFoundError) as excinfo:
        read_any_document(tmp_path)
    assert "dosya değil" in str(excinfo.value) or "not a file" in str(excinfo.value)


def test_epub_to_pdf_conversion(tmp_path: Path) -> None:
    src_epub = tmp_path / "sample.epub"
    build_sample_epub(src_epub)

    doc = read_any_document(src_epub)
    out_pdf = tmp_path / "sample.pdf"
    write_any_document(doc, src_epub, out_pdf)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 500


def test_docx_to_html_conversion(tmp_path: Path) -> None:
    src_docx = tmp_path / "sample.docx"
    build_sample_docx(src_docx)

    doc = read_any_document(src_docx)
    out_html = tmp_path / "sample.html"
    write_any_document(doc, src_docx, out_html)

    assert out_html.exists()
    content = out_html.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_image_input_and_pdf_output(tmp_path: Path) -> None:
    src_img = tmp_path / "test.png"
    img = Image.new("RGB", (200, 100), color="white")
    img.save(src_img)

    doc = read_any_document(src_img)
    assert doc.source_format == "image"
    assert len(doc.pages) == 1

    out_pdf = tmp_path / "test.pdf"
    write_any_document(doc, src_img, out_pdf)
    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 100


def test_epub_to_docx_conversion(tmp_path: Path) -> None:
    src_epub = tmp_path / "sample.epub"
    build_sample_epub(src_epub)

    doc = read_any_document(src_epub)
    out_docx = tmp_path / "sample.docx"
    write_any_document(doc, src_epub, out_docx)

    assert out_docx.exists()
    assert out_docx.stat().st_size > 500


def test_docx_to_pdf_conversion(tmp_path: Path) -> None:
    src_docx = tmp_path / "sample.docx"
    build_sample_docx(src_docx)

    doc = read_any_document(src_docx)
    out_pdf = tmp_path / "sample.pdf"
    write_any_document(doc, src_docx, out_pdf)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 500



def test_every_page_survives_conversion_to_images(tmp_path: Path) -> None:
    """A single image holds one page, so a multi-page source needs one file per page.

    Only `pdf_doc[0]` was rendered, and the caller was told the write had succeeded. A 15-page
    PDF became one PNG of its first page and the other fourteen were gone - after the pipeline
    had translated all of them. Nothing reported it, which is the worst outcome this project
    recognises: handing back a wrong document that looks right (CONTRACT.md).
    """
    import pymupdf

    src = Path("_artifacts/corpus/arxiv_1706.03762.pdf")
    if not src.exists():
        import pytest

        pytest.skip("corpus PDF not available")
    page_count = pymupdf.open(src).page_count
    assert page_count > 1

    doc = read_any_document(src)
    written = write_any_document(doc, src, tmp_path / "out.png")

    assert len(written) == page_count, f"{page_count} pages produced {len(written)} images"
    assert written[0] == tmp_path / "out.png", "the requested path must be the first page"
    assert all(p.exists() for p in written)
    # Distinct pages, not the same page written repeatedly.
    assert len({p.read_bytes() for p in written}) == page_count


def test_a_single_page_source_keeps_the_exact_requested_filename(tmp_path: Path) -> None:
    """The common case must not gain a number suffix it never had."""
    src = Path("_artifacts/input/single_column.pdf")
    if not src.exists():
        import pytest

        pytest.skip("fixture PDF not available")

    out = tmp_path / "page.png"
    written = write_any_document(read_any_document(src), src, out)

    assert written == [out]
    assert Image.open(out).size[0] > 0


def _pdf_with_figures() -> Path:
    src = Path("_artifacts/corpus/nasa_report.pdf")
    if not src.exists():
        import pytest

        pytest.skip("corpus PDF not available")
    return src


def test_the_reader_carries_image_bytes_not_just_their_positions() -> None:
    """DocIR held text and nothing else.

    The PDF reader already computed image bounding boxes, to help decide block roles, and threw
    the pixels away. That was invisible for as long as the only PDF writer edited a copy of the
    source - the figures were never removed, so nothing had to reproduce them - and it made
    carrying a figure into any other format impossible.
    """
    import pymupdf

    from layoutkeep.readers.pdf_reader import read_pdf

    src = _pdf_with_figures()
    expected = sum(len(p.get_images(full=True)) for p in pymupdf.open(src))
    assert expected > 0

    doc = read_pdf(src)
    images = [img for page in doc.pages for img in page.images]
    assert len(images) == expected
    assert all(img.data for img in images), "an image was carried without its bytes"


def test_figures_survive_conversion_to_html(tmp_path: Path) -> None:
    src = _pdf_with_figures()
    doc = read_any_document(src)
    expected = sum(len(p.images) for p in doc.pages)

    out = tmp_path / "o.html"
    write_any_document(doc, src, out)

    assert out.read_text(encoding="utf-8", errors="ignore").lower().count("<img") == expected


def test_figures_survive_conversion_to_epub(tmp_path: Path) -> None:
    import zipfile

    src = _pdf_with_figures()
    doc = read_any_document(src)
    expected = sum(len(p.images) for p in doc.pages)

    out = tmp_path / "o.epub"
    write_any_document(doc, src, out)

    with zipfile.ZipFile(out) as package:
        # ebooklib roots the package under EPUB/, so match on the item path we asked for.
        packaged = [n for n in package.namelist() if "/images/" in n]
        referenced = sum(
            package.read(n).decode("utf-8", "ignore").count("<img")
            for n in package.namelist()
            if n.endswith(".xhtml")
        )
    assert len(packaged) == expected
    assert referenced == expected


def test_an_image_only_page_does_not_take_the_whole_epub_export_down(tmp_path: Path) -> None:
    """ebooklib parses every chapter it writes, and lxml refuses an empty body.

    A page carrying a picture and no text produced no elements at all, so the export died with
    "Document is empty" - one such page in a 23-page report killed the entire conversion.
    """
    from layoutkeep.core.docir import Document, Page

    doc = Document(pages=[Page(number=1, width=200.0, height=200.0, blocks=[])])
    out = tmp_path / "empty.epub"

    write_any_document(doc, Path("source.pdf"), out)

    assert out.exists() and out.stat().st_size > 0


def test_figures_survive_conversion_to_docx(tmp_path: Path) -> None:
    """A DOCX carries pictures as separate parts wired through document.xml.rels.

    None of that plumbing existed: the package held three files, and every figure was dropped
    with no error. All three pieces have to agree or Word refuses the file - the media part, the
    relationship pointing at it, and the content-type declaring its extension.
    """
    import xml.dom.minidom
    import zipfile

    src = _pdf_with_figures()
    doc = read_any_document(src)
    expected = sum(len(p.images) for p in doc.pages)

    out = tmp_path / "o.docx"
    write_any_document(doc, src, out)

    with zipfile.ZipFile(out) as package:
        names = package.namelist()
        media = [n for n in names if n.startswith("word/media/")]
        document_xml = package.read("word/document.xml").decode("utf-8", "ignore")
        rels = package.read("word/_rels/document.xml.rels").decode("utf-8")
        content_types = package.read("[Content_Types].xml").decode("utf-8")
        for part in ("word/document.xml", "[Content_Types].xml", "word/_rels/document.xml.rels"):
            xml.dom.minidom.parseString(package.read(part))

    assert len(media) == expected
    assert document_xml.count("<w:drawing>") == expected
    assert rels.count("<Relationship ") == expected
    for extension in {n.rsplit(".", 1)[-1] for n in media}:
        assert f'Extension="{extension}"' in content_types


def test_images_round_trip_through_a_saved_project(tmp_path: Path) -> None:
    """A .lkproj must stay self-contained: re-exportable without the source (CONTRACT.md, D5)."""
    from layoutkeep.core.docir import load_project, save_project

    src = _pdf_with_figures()
    doc = read_any_document(src)
    expected = sum(len(p.images) for p in doc.pages)

    project = tmp_path / "p.lkproj"
    save_project(doc, project)
    reloaded = load_project(project)

    assert sum(len(p.images) for p in reloaded.pages) == expected
    assert all(img.data for page in reloaded.pages for img in page.images)
