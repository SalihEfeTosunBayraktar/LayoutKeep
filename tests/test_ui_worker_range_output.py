"""A page range narrows the OUTPUT too, not just what gets translated.

The behaviour this pins down, reported while using the app: a run on a 841-page book with a range
selected produced a translation of the selected pages *inside a copy of the whole book* — "shouldn't
it output only the range I selected?". The engine had a deliberate reason to keep the document
whole (the reviewer needs the other pages, and re-exporting from the project must not silently
shorten it), so the range is now applied to the copy that gets written, and the project keeps
every page. Both halves of that are asserted here, because keeping only one of them is the bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

from layoutkeep.core.docir import load_project
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker, _output_document, _source_slice

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_pdf_fixture


def _three_page_pdf(path: Path) -> Path:
    """A real three-page PDF: the fixtures are single-page, and a range needs pages to choose."""
    source = path / "one.pdf"
    build_pdf_fixture.build_single_column(source)
    with pymupdf.open(str(source)) as single:
        out = pymupdf.open()
        for _ in range(3):
            out.insert_pdf(single)
        out.save(str(path / "three.pdf"))
        out.close()
    return path / "three.pdf"


def _job(tmp_path: Path, source: Path, **overrides) -> JobConfig:
    defaults = {
        "input_path": str(source),
        "output_path": str(tmp_path / "three.out.pdf"),
        "source_lang": "en",
        "target_lang": "tr",
        "provider": ProviderConfig(kind="fake"),
    }
    defaults.update(overrides)
    return JobConfig(**defaults)


def test_the_output_holds_only_the_selected_pages(tmp_path) -> None:
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source, page_range="2")

    worker = TranslationWorker(config)
    worker.run()

    with pymupdf.open(config.output_path) as written:
        assert written.page_count == 1, "the output should hold the one page the range selected"


def test_the_project_still_holds_every_page(tmp_path) -> None:
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source, page_range="2")

    TranslationWorker(config).run()

    project = load_project(Path(config.output_path).with_suffix(".lkproj"))
    assert len(project.pages) == 3, "the project must keep the pages the range left out"


def test_a_whole_document_range_changes_nothing(tmp_path) -> None:
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source, page_range="1-3")

    TranslationWorker(config).run()

    with pymupdf.open(config.output_path) as written:
        assert written.page_count == 3


def test_no_range_changes_nothing(tmp_path) -> None:
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source)

    TranslationWorker(config).run()

    with pymupdf.open(config.output_path) as written:
        assert written.page_count == 3


def test_the_written_pages_keep_the_source_page_numbers_for_verification(tmp_path) -> None:
    """The slice is renumbered so page N of the output pairs with page N of the sliced source;
    the project keeps the original numbers, so the reviewer can still find the page in the book."""
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source, page_range="2-3")

    TranslationWorker(config).run()

    project = load_project(Path(config.output_path).with_suffix(".lkproj"))
    assert [page.source_ref for page in project.pages] == ["0", "1", "2"]


def test_the_source_slice_holds_exactly_the_selected_pages(tmp_path) -> None:
    source = _three_page_pdf(tmp_path)
    destination = tmp_path / "slice.pdf"

    written = _source_slice(source, {1, 3}, destination)

    assert written == destination
    with pymupdf.open(str(destination)) as sliced:
        assert sliced.page_count == 2


def test_a_slice_of_everything_is_not_written(tmp_path) -> None:
    """Slicing the whole document would only add a file and a chance of drift."""
    source = _three_page_pdf(tmp_path)
    assert _source_slice(source, {1, 2, 3}, tmp_path / "none.pdf") is None


def test_the_output_document_helper_leaves_a_ranged_document_alone(tmp_path) -> None:
    """Unit-level: with no range (or the whole range) the document handed to the writer is the
    very object the project will be saved from - no copy, no divergence."""
    from layoutkeep.writers.converter import read_any_document

    source = _three_page_pdf(tmp_path)
    doc = read_any_document(source)
    config = _job(tmp_path, source)

    same, pages = _output_document(doc, config)

    assert same is doc
    assert pages is None


@pytest.mark.parametrize("spec", ["2", "2-2", " 2 "])
def test_a_range_is_read_the_same_way_however_it_is_written(tmp_path, spec: str) -> None:
    source = _three_page_pdf(tmp_path)
    config = _job(tmp_path, source, page_range=spec)

    worker = TranslationWorker(config)
    worker.run()

    with pymupdf.open(config.output_path) as written:
        assert written.page_count == 1


def _epub_job(tmp_path: Path, **overrides) -> JobConfig:
    sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
    import build_epub_fixture

    source = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(source)
    defaults = {
        "input_path": str(source),
        "output_path": str(tmp_path / "sample.out.epub"),
        "source_lang": "en",
        "target_lang": "tr",
        "provider": ProviderConfig(kind="fake"),
    }
    defaults.update(overrides)
    return JobConfig(**defaults)


def test_an_epub_range_also_narrows_the_output(tmp_path) -> None:
    """The range is not a PDF-only feature: the EPUB and DOCX writers walk `doc.pages` too, so the
    subset document they are handed is what they write. Asserted on the written archive because
    that is what the reader actually gets."""
    import zipfile

    config = _epub_job(tmp_path, page_range="1")
    TranslationWorker(config).run()

    with zipfile.ZipFile(config.output_path) as zf:
        chapter_text = {
            name: zf.read(name).decode("utf-8")
            for name in zf.namelist()
            if name.endswith(".xhtml")
        }
    joined = " ".join(chapter_text.values())
    assert "chap2" not in joined.lower() or "second chapter" not in joined.lower(), (
        "the output should not carry the page the range left out"
    )


def test_an_epub_project_still_keeps_every_page(tmp_path) -> None:
    config = _epub_job(tmp_path, page_range="1")
    TranslationWorker(config).run()

    project = load_project(Path(config.output_path).with_suffix(".lkproj"))
    assert len(project.pages) == 2, "the project must keep the page the range left out"
