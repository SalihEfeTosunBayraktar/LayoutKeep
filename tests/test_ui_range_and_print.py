"""Tests for UI range selection (printing was removed with the review editor)."""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.ui.job_setup import JobSetupWidget


def test_job_setup_range_selection(qtbot, tmp_path, monkeypatch):
    # Aralık seçim arayüzünü ve sinyalini test eder / Tests range selector UI
    #
    # The fake provider is selected deliberately. `_emit_job` validates first and opens a modal
    # QMessageBox when the form is incomplete, and the default provider is "openai" with no
    # model set - so without this the dialog blocks forever with nobody to dismiss it, and the
    # whole test suite hangs rather than failing. See test_ui_job_setup.py, which either selects
    # the fake provider or monkeypatches QMessageBox.warning for exactly this reason.
    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    combo = widget._provider_profile_combo
    combo.select_profile(next(p.name for p in combo.profiles() if p.kind == "fake"))

    # Başlangıçta tüm belge seçilidir ve metin kutusu gizlidir
    assert widget._range_mode.currentIndex() == 0
    assert widget._range_input.isHidden()

    # Özel aralığa geçildiğinde görünür olmalı
    widget._range_mode.setCurrentIndex(1)
    assert not widget._range_input.isHidden()
    widget._range_input.setText("1-5, 8")

    # A page range is a PDF idea, and PDF to PDF is the pair this build enables; a locked pair
    # is refused before a job is ever emitted.
    src = tmp_path / "in.pdf"
    src.write_text("sample")
    widget._input_path.setText(str(src))
    widget._output_path.setText(str(tmp_path / "out.pdf"))

    received_config = []
    widget.job_ready.connect(received_config.append)
    widget._emit_job()

    assert len(received_config) == 1
    assert received_config[0].page_range == "1-5, 8"


def test_a_page_range_narrows_both_the_translation_and_the_output(tmp_path):
    """Selecting pages 1-2: the output holds those two pages, the project holds all fifteen.

    Two opposite mistakes have been made here, and the test now pins both halves. First the range
    rebuilt the Document from the selected pages only: the output looked right (it is written into
    a copy of the source, so it kept all 15 pages) while the saved project held just 2, so the
    reviewer could not see or correct the rest and re-exporting silently produced a 2-page document
    (CONTRACT.md, D5). Then, to protect the project, the range narrowed only the *translation* -
    and a run over a 841-page book with a range selected handed back a copy of the whole book with
    a few pages translated, reported as "shouldn't it output only the range I selected?". The
    project keeps every page, the output holds the range, and both are asserted here.
    """
    import pymupdf

    from layoutkeep.core.docir import load_project
    from layoutkeep.ui.job import JobConfig, ProviderConfig
    from layoutkeep.ui.worker import TranslationWorker

    src = Path("_artifacts/corpus/arxiv_1706.03762.pdf")
    if not src.exists():
        pytest.skip("corpus PDF not available")
    assert pymupdf.open(src).page_count == 15

    out = tmp_path / "ranged.pdf"
    project = tmp_path / "ranged.lkproj"
    TranslationWorker(
        JobConfig(
            input_path=str(src),
            output_path=str(out),
            source_lang="en",
            target_lang="tr",
            provider=ProviderConfig(kind="fake"),
            page_range="1-2",
            project_path=str(project),
        )
    ).run()

    assert len(load_project(project).pages) == 15, "project lost the unselected pages"

    exported = pymupdf.open(out)
    assert exported.page_count == 2, "the output should hold only the selected pages"
    translated = [p.get_text().count("[tr]") + p.get_text().count("TR:") for p in exported]
    assert all(n > 0 for n in translated), "selected pages were not translated"
