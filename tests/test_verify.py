"""The application checks what it wrote, asks again for what a translation lost, flags the rest.

The loss criteria used to run only in the campaign's audit tool, after the fact: a document
translated in the application got none of it, and a reply in the wrong language or a paragraph
drawn over another reached the user unmarked.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf

from layoutkeep.core.docir import apply_segments, segments_from_document
from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.verify import REVIEW_REASONS, output_losses, translation_losses, verify_and_repair

_ENGLISH = "Information security is the protection of information and systems from unauthorized access."
_TURKISH = "Bilgi güvenliği, bilgi ve sistemlerin yetkisiz erişime karşı korunması için bir önlemdir."
_GERMAN = "Die Informationssicherheit ist der Schutz von Informationen und Systemen vor dem Zugriff."


def _source(path: Path, *paragraphs: tuple[float, str]) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for top, text in paragraphs:
        page.insert_text((72, top), text, fontsize=10)
    doc.save(str(path))
    return path


def _translated(src: Path, *targets: str):
    doc = read_pdf(src)
    segments = segments_from_document(doc)
    for segment, target in zip(segments, targets, strict=True):
        segment.target = target
    apply_segments(doc, segments)
    return doc, segments


def test_a_reply_in_another_language_is_a_loss_and_is_flagged_with_its_reason(tmp_path: Path) -> None:
    doc, segments = _translated(_source(tmp_path / "s.pdf", (100, _ENGLISH)), _GERMAN)

    assert [loss.kind for loss in translation_losses(doc, "tr")] == ["L2"]

    report = verify_and_repair(doc, segments, target_lang="tr", write=lambda: None)
    block = doc.pages[0].blocks[0]
    assert report.remaining["L2"] == 1 and not report.lossless
    assert block.needs_review and REVIEW_REASONS["L2"] in block.review_reason
    assert segments[0].needs_review


def test_a_number_the_translation_lost_is_a_loss(tmp_path: Path) -> None:
    doc, _ = _translated(
        _source(tmp_path / "s.pdf", (100, "Section 3.12 describes the 4 roles of an information security architect.")),
        "Bölüm, bilgi güvenliği mimarının rollerini ve bu rollerin sorumluluklarını açıklar.",
    )
    assert "L6" in [loss.kind for loss in translation_losses(doc, "tr")]


def test_asking_again_mends_the_reply_and_writes_the_document_again(tmp_path: Path) -> None:
    doc, segments = _translated(_source(tmp_path / "s.pdf", (100, _ENGLISH)), _ENGLISH)
    writes: list[int] = []

    def ask_again(again):
        for segment in again:
            segment.target = _TURKISH
        return len(again)

    report = verify_and_repair(
        doc, segments, target_lang="tr", write=lambda: writes.append(1), ask_again=ask_again
    )

    assert report.repaired == 1 and report.lossless, report
    assert writes == [1]
    assert doc.pages[0].blocks[0].text.replace("\n", " ") == _TURKISH
    assert not doc.pages[0].blocks[0].needs_review


def test_a_request_that_mends_nothing_is_not_repeated(tmp_path: Path) -> None:
    doc, segments = _translated(_source(tmp_path / "s.pdf", (100, _ENGLISH)), _ENGLISH)
    asked: list[int] = []

    def ask_again(again):
        asked.append(len(again))
        return 0

    report = verify_and_repair(
        doc, segments, target_lang="tr", write=lambda: None, ask_again=ask_again, rounds=3
    )
    assert asked == [1] and report.remaining["L2"] == 1
    assert doc.pages[0].blocks[0].needs_review


def test_a_translation_missing_from_the_written_page_was_dropped_by_the_writer(tmp_path: Path) -> None:
    src = _source(tmp_path / "s.pdf", (100, _ENGLISH))
    doc, _ = _translated(src, _TURKISH)
    out = tmp_path / "o.pdf"
    shutil.copyfile(src, out)  # the page as if the writer drew nothing

    losses = output_losses(src, out, doc)
    assert [(loss.kind, loss.block_ids) for loss in losses if loss.kind == "L3"] == [
        ("L3", (doc.pages[0].blocks[0].id,))
    ]


def test_text_drawn_over_another_block_names_the_block_underneath(tmp_path: Path) -> None:
    src = _source(tmp_path / "s.pdf", (100, _ENGLISH), (300, "Security controls are safeguards for an information system."))
    doc, _ = _translated(src, _TURKISH, "Güvenlik kontrolleri, bir bilgi sistemi için alınan önlemlerdir.")
    out = tmp_path / "o.pdf"
    with pymupdf.open(str(src)) as written:
        page = written[0]
        page.insert_text((72, 100), _TURKISH, fontsize=10)
        page.insert_text((72, 300), "Güvenlik kontrolleri, bir bilgi sistemi için alınan önlemlerdir.", fontsize=10)
        # The first translation ran long and was drawn down over the second paragraph.
        page.insert_text((74, 301), "yetkisiz erişime karşı korunması için bir önlemdir ve daha fazlası", fontsize=10)
        written.save(str(out))

    overlaps = [loss for loss in output_losses(src, out, doc) if loss.kind == "L7"]
    assert overlaps, "text drawn over text was not found"
    assert doc.pages[0].blocks[1].id in overlaps[0].block_ids


def test_untouched_text_that_moved_is_found(tmp_path: Path) -> None:
    src = _source(tmp_path / "s.pdf", (100, _ENGLISH), (400, "Figure 3.1"))
    doc, _ = _translated(src, _TURKISH, "Figure 3.1")
    out = tmp_path / "o.pdf"
    with pymupdf.open(str(src)) as written:
        page = written[0]
        page.add_redact_annot(pymupdf.Rect(60, 385, 300, 405))
        page.apply_redactions()
        page.insert_text((72, 412), "Figure 3.1", fontsize=10)  # one line lower than it was
        written.save(str(out))

    moved = [loss for loss in output_losses(src, out, doc) if loss.kind == "L8"]
    assert moved and moved[0].block_ids == (doc.pages[0].blocks[1].id,)


def test_a_letter_from_another_alphabet_is_a_loss_asked_for_again(tmp_path: Path) -> None:
    doc, segments = _translated(
        _source(tmp_path / "s.pdf", (100, "MECHANICAL ENGINEER")), "MAKİNE MÜHENДİSİ"
    )
    assert [loss.kind for loss in translation_losses(doc, "tr")] == ["L9"]

    def ask_again(again):
        for segment in again:
            segment.target = "MAKİNE MÜHENDİSİ"
        return len(again)

    report = verify_and_repair(doc, segments, target_lang="tr", write=lambda: None, ask_again=ask_again)
    assert report.repaired == 1 and report.lossless



def test_words_that_already_overlap_in_the_source_are_not_drawn_over_each_other() -> None:
    """Held-out arXiv 2609.19145: display equations set a superscript over a subscript, so their
    glyph boxes overlap on the source page itself, in separate text blocks. The page kept them
    untouched, and verification flagged 11 overlapping pairs on it - all the source's typesetting."""
    from layoutkeep.verify import overlapping_words

    superscript = (306.0, 336.0, 344.0, 350.0, "Gll(D)", 8, 0, 0)
    subscript = (315.0, 345.0, 333.0, 353.0, "s1,s2", 9, 0, 0)
    source = [superscript, subscript]
    assert overlapping_words(source)[0] == 1  # the source's own overlap
    assert overlapping_words(source, as_in=source)[0] == 0

    translation = (310.0, 340.0, 360.0, 352.0, "erişim", 12, 0, 0)  # drawn over the equation
    assert overlapping_words([superscript, subscript, translation], as_in=source)[0] == 2
