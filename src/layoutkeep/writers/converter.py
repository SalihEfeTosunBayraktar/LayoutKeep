"""Document converter and exporter: orchestrates readers and writers for any format pair.

Herhangi bir girdi ve çıktı formatı arasında dönüştürme ve kaydetmeyi yöneten orkestrasyon modülü.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from layoutkeep.core.docir import Document, load_project, save_project

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"})
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".epub", ".docx", ".html", ".htm", ".lkproj"})
SUPPORTED_INPUT_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS


def read_any_document(path: Path) -> Document:
    # Desteklenen herhangi bir formattaki dosyayı DocIR'e okur / Reads any supported file into DocIR
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Girdi dosyası bulunamadı / Input file not found: {path}"
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"Girdi bir dosya değil / Input is not a file: {path}"
        )
    suffix = path.suffix.lower()
    if suffix == ".lkproj":
        return load_project(path)
    if suffix == ".epub":
        from layoutkeep.readers.epub_reader import read_epub
        return read_epub(path)
    if suffix == ".pdf":
        from layoutkeep.readers.pdf_reader import read_pdf
        return read_pdf(path)
    if suffix == ".docx":
        from layoutkeep.readers.docx_reader import read_docx
        return read_docx(path)
    if suffix in IMAGE_EXTENSIONS:
        from layoutkeep.readers.image_reader import read_image
        return read_image(path)
    raise ValueError(f"Desteklenmeyen dosya türü / Unsupported file type: {suffix}")


def _write_pdf_target(doc: Document, source: Path, out: Path) -> None:
    # PDF çıktısını kaynak türe göre yazar / Writes PDF target according to source type
    src_suffix = source.suffix.lower()
    if src_suffix == ".pdf":
        from layoutkeep.writers.pdf_writer import write_pdf
        write_pdf(doc, source, out)
    elif src_suffix in IMAGE_EXTENSIONS:
        from layoutkeep.writers.image_writer import write_image
        write_image(doc, source, out)
    elif src_suffix == ".epub":
        # EPUB → PDF: reflowable document. MuPDF's `layout()` re-flows but drops page-breaks,
        # so chapters land mid-page. `generate_reflowed_pdf_from_docir` uses the Story API which
        # honours `page-break-before` and inlines the EPUB's images as data URIs, so chapters
        # start fresh pages and figures survive — the source's CSS font sizes and alignment are
        # carried by the reader (see readers/_epub_css.py).
        from layoutkeep.writers.pdf_generator import generate_reflowed_pdf_from_docir
        out.parent.mkdir(parents=True, exist_ok=True)
        generate_reflowed_pdf_from_docir(doc, out)
    else:
        from layoutkeep.writers.pdf_generator import generate_pdf_from_docir
        generate_pdf_from_docir(doc, out)


def _write_docx_target(doc: Document, source: Path, out: Path) -> None:
    # DOCX çıktısını kaynak türe göre yazar / Writes DOCX target according to source type
    if source.suffix.lower() == ".docx":
        from layoutkeep.writers.docx_writer import write_docx
        write_docx(doc, source, out)
    else:
        from layoutkeep.writers.docx_generator import generate_docx_from_docir
        generate_docx_from_docir(doc, out)


def _write_epub_target(doc: Document, source: Path, out: Path) -> None:
    # EPUB çıktısını kaynak türe göre yazar / Writes EPUB target according to source type
    if source.suffix.lower() == ".epub":
        from layoutkeep.writers.epub_writer import write_epub
        write_epub(doc, source, out)
    else:
        from layoutkeep.writers.epub_generator import generate_epub_from_docir
        generate_epub_from_docir(doc, out)


#: Rendering resolution for document-to-image conversion.
_IMAGE_DPI = 150


def _write_image_target(doc: Document, source: Path, out: Path) -> list[Path]:
    """Render the document to images, one file per page. Returns every file written.

    A single image holds one page, so a multi-page source needs more than one file. Rendering
    only `pdf_doc[0]` and reporting success turned a 15-page PDF into one PNG of its first page
    with the other fourteen silently gone - the pipeline had translated all of them first.

    The first page keeps the exact path that was asked for, so a single-page document behaves
    as before and the caller's "wrote <out>" stays true. Further pages sit beside it as
    `<stem>-002<ext>`, `<stem>-003<ext>` and so on.

    Görsel çıktısını sayfa başına bir dosya olarak yazar / Writes one image file per page.
    """
    if source.suffix.lower() in IMAGE_EXTENSIONS:
        from layoutkeep.writers.image_writer import write_image
        write_image(doc, source, out)
        return [out]

    import pymupdf
    written: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_pdf = Path(tmp_dir) / "render.pdf"
        _write_pdf_target(doc, source, tmp_pdf)
        out.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(str(tmp_pdf)) as pdf_doc:
            for number, page in enumerate(pdf_doc, start=1):
                target = out if number == 1 else out.with_name(
                    f"{out.stem}-{number:03d}{out.suffix}"
                )
                page.get_pixmap(dpi=_IMAGE_DPI).save(str(target))
                written.append(target)
    return written


def write_any_document(doc: Document, source: Path, out: Path) -> list[Path]:
    """Dispatch to the writer for the target format. Returns every file written.

    Almost every format produces the single file that was asked for. Images are the exception:
    one page per file, so a multi-page source yields several.

    Hedef dosya uzantısına göre en uygun yazıcıyı çalıştırır / Dispatches writer based on target
    """
    out_suffix = out.suffix.lower()
    if out_suffix == ".lkproj":
        save_project(doc, out)
        return [out]
    if out_suffix in {".html", ".htm"}:
        from layoutkeep.writers.html_writer import write_html
        write_html(doc, source, out)
        return [out]
    if out_suffix == ".pdf":
        _write_pdf_target(doc, source, out)
        return [out]
    if out_suffix == ".docx":
        _write_docx_target(doc, source, out)
        return [out]
    if out_suffix == ".epub":
        _write_epub_target(doc, source, out)
        return [out]
    if out_suffix in IMAGE_EXTENSIONS:
        return _write_image_target(doc, source, out)
    raise ValueError(f"Desteklenmeyen çıktı türü / Unsupported output format: {out_suffix}")
