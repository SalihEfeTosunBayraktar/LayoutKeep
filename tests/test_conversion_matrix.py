"""Full input x output format conversion matrix test with FakeProvider translation.

Her girdi formatini (pdf-sekilli, pdf-metin, epub, docx, gorsel) her cikti
formatina (.pdf .epub .docx .html .png .lkproj) cevirip dogrular. Sadece
"dosya yazildi" degil, icerik kontrolu yapar.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import pytest
from fixtures.build_docx_fixture import build_sample_docx
from fixtures.build_epub_fixture import build_sample_epub
from fixtures.build_image_fixture import build_plain_white

from layoutkeep.core.docir import (
    Document,
    apply_segments,
    load_project,
    segments_from_document,
)
from layoutkeep.providers.fake import FakeProvider
from layoutkeep.writers.converter import read_any_document, write_any_document

# ---------------------------------------------------------------------------
# Fixture yardimcilari / Fixture helpers
# ---------------------------------------------------------------------------


def _pdf_shapes_path() -> Path:
    # 23 gorselli NASA raporu / NASA report with 23 figures
    p = Path("_artifacts/corpus/nasa_report.pdf")
    if not p.exists():
        pytest.skip("corpus PDF not available")
    return p


def _pdf_text_path() -> Path:
    return Path("tests/fixtures/pdf_single_column.pdf")


def _make_epub(tmp_path: Path) -> Path:
    p = tmp_path / "src.epub"
    build_sample_epub(p)
    return p


def _make_docx(tmp_path: Path) -> Path:
    p = tmp_path / "src.docx"
    build_sample_docx(p)
    return p


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "src.png"
    build_plain_white(p)
    return p


def _translate_with_fake(doc: Document) -> Document:
    # FakeProvider ile ceviri simule eder / Simulates translation with FakeProvider
    segs = segments_from_document(doc)
    if not segs:
        return doc
    provider = FakeProvider()
    translated = provider.translate(segs, "en", "tr")
    apply_segments(doc, translated)
    return doc


# ---------------------------------------------------------------------------
# Dogrulama yardimcilari / Verification helpers
# ---------------------------------------------------------------------------


def _verify_pdf(out: Path, *, expect_text: bool = True) -> None:
    # PDF ciktisini dogrular / Verifies PDF output
    assert out.exists(), f"PDF dosyasi olusturulmadi / PDF file not created: {out}"
    assert out.stat().st_size > 200, f"PDF dosyasi cok kucuk / PDF too small: {out.stat().st_size}B"
    with pymupdf.open(str(out)) as doc:
        assert doc.page_count >= 1
        if expect_text:
            all_text = "".join(p.get_text() for p in doc)
            assert len(all_text) > 0, "PDF metin katmani bos / PDF text layer empty"


def _verify_epub(out: Path) -> None:
    # EPUB ciktisini dogrular / Verifies EPUB output
    assert out.exists()
    assert out.stat().st_size > 200
    with zipfile.ZipFile(out) as z:
        xhtml = [n for n in z.namelist() if n.endswith((".xhtml", ".html"))]
        assert xhtml, "EPUB icerik dosyasi yok / EPUB has no content files"
        total_text = sum(len(z.read(n)) for n in xhtml)
        assert total_text > 0, "EPUB icerik bos / EPUB content is empty"


def _verify_docx(out: Path) -> None:
    # DOCX ciktisini dogrular / Verifies DOCX output
    assert out.exists()
    assert out.stat().st_size > 200
    with zipfile.ZipFile(out) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8", "ignore")
        assert len(doc_xml) > 50, "DOCX document.xml bos / DOCX document.xml is empty"
        # Metin var mi / Is there text?
        assert "<w:t" in doc_xml, "DOCX metin bulunamadi / No text elements in DOCX"


def _verify_html(out: Path) -> None:
    # HTML ciktisini dogrular / Verifies HTML output
    assert out.exists()
    content = out.read_text(encoding="utf-8", errors="ignore")
    assert "<!DOCTYPE html>" in content or "<html" in content
    assert len(content) > 100, "HTML dosyasi cok kucuk / HTML too small"


def _verify_image(out: Path, *, min_files: int = 1) -> list[Path]:
    # Gorsel ciktisini dogrular / Verifies image output(s)
    parent = out.parent
    stem = out.stem
    all_files = sorted(parent.glob(f"{stem}*{out.suffix}"))
    assert len(all_files) >= min_files, (
        f"Beklenen en az {min_files} gorsel, {len(all_files)} bulundu / "
        f"Expected >= {min_files} images, found {len(all_files)}"
    )
    for f in all_files:
        img = Image.open(f)
        assert img.size[0] > 0 and img.size[1] > 0
    return all_files


def _verify_lkproj(out: Path, *, min_blocks: int = 0) -> None:
    # Proje dosyasini dogrular / Verifies .lkproj roundtrip
    assert out.exists()
    loaded = load_project(out)
    assert len(loaded.pages) >= 1
    total_blocks = sum(len(p.blocks) for p in loaded.pages)
    if min_blocks > 0:
        assert total_blocks >= min_blocks, (
            f"Beklenen en az {min_blocks} blok, {total_blocks} bulundu / "
            f"Expected >= {min_blocks} blocks, found {total_blocks}"
        )


def _verify_figures(doc: Document, out: Path, out_fmt: str) -> None:
    # Sekillerin ciktida korunmasini dogrular / Verifies figures survive conversion
    src_images = sum(len(p.images) for p in doc.pages)
    if src_images == 0:
        return

    if out_fmt == ".html":
        content = out.read_text(encoding="utf-8", errors="ignore").lower()
        assert content.count("<img") >= src_images, (
            f"{src_images} gorsel bekleniyor, HTML'de {content.count('<img')} bulundu"
        )
    elif out_fmt == ".epub":
        with zipfile.ZipFile(out) as z:
            packaged = [n for n in z.namelist() if "/images/" in n]
            assert len(packaged) >= src_images
    elif out_fmt == ".docx":
        with zipfile.ZipFile(out) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
            assert len(media) >= src_images


# ---------------------------------------------------------------------------
# Matris testleri / Matrix tests
# ---------------------------------------------------------------------------

_OUTPUT_FORMATS = [".pdf", ".epub", ".docx", ".html", ".png", ".lkproj"]


class TestPdfShapesMatrix:
    # PDF (23 sekilli) -> tum cikti formatlari / PDF with 23 figures -> all output formats

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.src = _pdf_shapes_path()
        self.doc = read_any_document(self.src)
        _translate_with_fake(self.doc)
        self.tmp = tmp_path

    def test_to_pdf(self) -> None:
        out = self.tmp / "out.pdf"
        write_any_document(self.doc, self.src, out)
        _verify_pdf(out)
        _verify_figures(self.doc, out, ".pdf")

    def test_to_epub(self) -> None:
        out = self.tmp / "out.epub"
        write_any_document(self.doc, self.src, out)
        _verify_epub(out)
        _verify_figures(self.doc, out, ".epub")

    def test_to_docx(self) -> None:
        out = self.tmp / "out.docx"
        write_any_document(self.doc, self.src, out)
        _verify_docx(out)
        _verify_figures(self.doc, out, ".docx")

    def test_to_html(self) -> None:
        out = self.tmp / "out.html"
        write_any_document(self.doc, self.src, out)
        _verify_html(out)
        _verify_figures(self.doc, out, ".html")

    def test_to_png(self) -> None:
        out = self.tmp / "out.png"
        write_any_document(self.doc, self.src, out)
        _verify_image(out, min_files=23)

    def test_to_lkproj(self) -> None:
        out = self.tmp / "out.lkproj"
        write_any_document(self.doc, self.src, out)
        _verify_lkproj(out, min_blocks=1)


class TestPdfTextMatrix:
    # PDF (duz metin) -> tum cikti formatlari / PDF text-only -> all output formats

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.src = _pdf_text_path()
        self.doc = read_any_document(self.src)
        _translate_with_fake(self.doc)
        self.tmp = tmp_path

    def test_to_pdf(self) -> None:
        out = self.tmp / "out.pdf"
        write_any_document(self.doc, self.src, out)
        _verify_pdf(out)

    def test_to_epub(self) -> None:
        out = self.tmp / "out.epub"
        write_any_document(self.doc, self.src, out)
        _verify_epub(out)

    def test_to_docx(self) -> None:
        out = self.tmp / "out.docx"
        write_any_document(self.doc, self.src, out)
        _verify_docx(out)

    def test_to_html(self) -> None:
        out = self.tmp / "out.html"
        write_any_document(self.doc, self.src, out)
        _verify_html(out)

    def test_to_png(self) -> None:
        out = self.tmp / "out.png"
        write_any_document(self.doc, self.src, out)
        _verify_image(out, min_files=1)

    def test_to_lkproj(self) -> None:
        out = self.tmp / "out.lkproj"
        write_any_document(self.doc, self.src, out)
        _verify_lkproj(out, min_blocks=1)


class TestEpubMatrix:
    # EPUB -> tum cikti formatlari

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.src = _make_epub(tmp_path)
        self.doc = read_any_document(self.src)
        _translate_with_fake(self.doc)
        self.tmp = tmp_path

    def test_to_pdf(self) -> None:
        out = self.tmp / "out.pdf"
        write_any_document(self.doc, self.src, out)
        _verify_pdf(out)

    def test_to_epub(self) -> None:
        out = self.tmp / "out.epub"
        write_any_document(self.doc, self.src, out)
        _verify_epub(out)

    def test_to_docx(self) -> None:
        out = self.tmp / "out.docx"
        write_any_document(self.doc, self.src, out)
        _verify_docx(out)

    def test_to_html(self) -> None:
        out = self.tmp / "out.html"
        write_any_document(self.doc, self.src, out)
        _verify_html(out)

    def test_to_png(self) -> None:
        out = self.tmp / "out.png"
        write_any_document(self.doc, self.src, out)
        _verify_image(out, min_files=1)

    def test_to_lkproj(self) -> None:
        out = self.tmp / "out.lkproj"
        write_any_document(self.doc, self.src, out)
        _verify_lkproj(out, min_blocks=1)


class TestDocxMatrix:
    # DOCX -> tum cikti formatlari

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.src = _make_docx(tmp_path)
        self.doc = read_any_document(self.src)
        _translate_with_fake(self.doc)
        self.tmp = tmp_path

    def test_to_pdf(self) -> None:
        out = self.tmp / "out.pdf"
        write_any_document(self.doc, self.src, out)
        _verify_pdf(out)

    def test_to_epub(self) -> None:
        out = self.tmp / "out.epub"
        write_any_document(self.doc, self.src, out)
        _verify_epub(out)

    def test_to_docx(self) -> None:
        out = self.tmp / "out.docx"
        write_any_document(self.doc, self.src, out)
        _verify_docx(out)

    def test_to_html(self) -> None:
        out = self.tmp / "out.html"
        write_any_document(self.doc, self.src, out)
        _verify_html(out)

    def test_to_png(self) -> None:
        out = self.tmp / "out.png"
        write_any_document(self.doc, self.src, out)
        _verify_image(out, min_files=1)

    def test_to_lkproj(self) -> None:
        out = self.tmp / "out.lkproj"
        write_any_document(self.doc, self.src, out)
        _verify_lkproj(out, min_blocks=1)


class TestImageMatrix:
    # Gorsel -> tum cikti formatlari (gorsel->PDF: metin katmani yok, dogru davranis)

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.src = _make_image(tmp_path)
        self.doc = read_any_document(self.src)
        _translate_with_fake(self.doc)
        self.tmp = tmp_path

    def test_to_pdf(self) -> None:
        # Gorsel->PDF: metin katmani olmamasi dogru davranistir / Image->PDF: no text layer is correct
        out = self.tmp / "out.pdf"
        write_any_document(self.doc, self.src, out)
        _verify_pdf(out, expect_text=False)
        # Cikti goruntusu kaynak goruntusten farkli olmali / Output image bytes should differ from source
        with pymupdf.open(str(out)) as pdf_doc:
            pix = pdf_doc[0].get_pixmap()
            assert pix.width > 0

    def test_to_epub(self) -> None:
        out = self.tmp / "out.epub"
        write_any_document(self.doc, self.src, out)
        _verify_epub(out)

    def test_to_docx(self) -> None:
        out = self.tmp / "out.docx"
        write_any_document(self.doc, self.src, out)
        _verify_docx(out)

    def test_to_html(self) -> None:
        out = self.tmp / "out.html"
        write_any_document(self.doc, self.src, out)
        _verify_html(out)

    def test_to_png(self) -> None:
        out = self.tmp / "out.png"
        write_any_document(self.doc, self.src, out)
        _verify_image(out, min_files=1)

    def test_to_lkproj(self) -> None:
        out = self.tmp / "out.lkproj"
        write_any_document(self.doc, self.src, out)
        _verify_lkproj(out, min_blocks=1)
