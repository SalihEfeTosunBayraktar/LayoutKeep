"""The bilingual PDF: source and translation in one file.

Two properties matter and are asserted separately: the page geometry (side by side doubles the
width, alternating doubles the count) and the content (the left half really is the source page).
The third test is the one that keeps the feature honest - a half-finished run must compose only
the pages both documents have, rather than emitting a document shorter than either without saying
so.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from layoutkeep.writers.dual_pdf import compose_dual


def _page_pdf(path: Path, pages: int, text: str, width: float = 300.0) -> Path:
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page(width=width, height=400)
        page.insert_text((20, 60), f"{text} page {index + 1}", fontsize=14)
    doc.save(str(path))
    doc.close()
    return path


def test_side_by_side_doubles_the_width_and_keeps_the_page_count(tmp_path) -> None:
    source = _page_pdf(tmp_path / "src.pdf", 3, "ORIGINAL")
    translated = _page_pdf(tmp_path / "tr.pdf", 3, "CEVIRI")
    out = tmp_path / "dual.pdf"

    pages = compose_dual(source, translated, out, "side")

    assert pages == 3
    with pymupdf.open(str(out)) as dual, pymupdf.open(str(source)) as src:
        assert dual.page_count == src.page_count
        assert dual[0].rect.width == pytest.approx(src[0].rect.width * 2, abs=1.0)
        assert dual[0].rect.height == pytest.approx(src[0].rect.height, abs=1.0)


def test_the_left_half_is_the_source_and_the_right_half_the_translation(tmp_path) -> None:
    source = _page_pdf(tmp_path / "src.pdf", 2, "ORIGINAL")
    translated = _page_pdf(tmp_path / "tr.pdf", 2, "CEVIRI")
    out = tmp_path / "dual.pdf"

    compose_dual(source, translated, out, "side")

    with pymupdf.open(str(out)) as dual:
        page = dual[0]
        left = pymupdf.Rect(0, 0, page.rect.width / 2, page.rect.height)
        words_left = " ".join(w[4] for w in page.get_text("words") if w[0] < page.rect.width / 2)
        words_right = " ".join(w[4] for w in page.get_text("words") if w[0] >= page.rect.width / 2)
    assert "ORIGINAL" in words_left, "the source page should be on the left"
    assert "CEVIRI" in words_right, "the translation should be on the right"
    assert "CEVIRI" not in words_left


def test_alternating_doubles_the_page_count_and_keeps_the_size(tmp_path) -> None:
    source = _page_pdf(tmp_path / "src.pdf", 2, "ORIGINAL")
    translated = _page_pdf(tmp_path / "tr.pdf", 2, "CEVIRI")
    out = tmp_path / "dual.pdf"

    pages = compose_dual(source, translated, out, "alternate")

    assert pages == 2
    with pymupdf.open(str(out)) as dual, pymupdf.open(str(source)) as src:
        assert dual.page_count == src.page_count * 2
        assert dual[0].rect.width == pytest.approx(src[0].rect.width, abs=1.0)
        first = " ".join(w[4] for w in dual[0].get_text("words"))
        second = " ".join(w[4] for w in dual[1].get_text("words"))
    assert "ORIGINAL" in first and "CEVIRI" in second


def test_a_half_finished_run_composes_only_the_pages_both_have(tmp_path) -> None:
    """A run interrupted at page 4 of 10 must not produce a 10-page bilingual file whose last six
    pages show the source twice, nor a 4-page one without saying so."""
    source = _page_pdf(tmp_path / "src.pdf", 10, "ORIGINAL")
    translated = _page_pdf(tmp_path / "tr.pdf", 4, "CEVIRI")
    out = tmp_path / "dual.pdf"

    pages = compose_dual(source, translated, out, "side")

    assert pages == 4
    with pymupdf.open(str(out)) as dual:
        assert dual.page_count == 4


def test_an_unknown_mode_is_refused(tmp_path) -> None:
    source = _page_pdf(tmp_path / "src.pdf", 1, "ORIGINAL")
    translated = _page_pdf(tmp_path / "tr.pdf", 1, "CEVIRI")

    with pytest.raises(ValueError):
        compose_dual(source, translated, tmp_path / "dual.pdf", "stacked")

# The zero-page guard in `compose_dual` has no test: PyMuPDF refuses to *save* a page-less PDF
# ("cannot save with zero pages"), so the input it protects against cannot be built. The guard
# stays because the function is public and the alternative is an IndexError.
