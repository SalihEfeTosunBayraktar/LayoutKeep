"""Tests for format selection and persistent settings in JobSetupWidget."""

from __future__ import annotations

from layoutkeep.ui.job_setup import JobSetupWidget


def test_format_selection_updates_output_path(qtbot, tmp_path):
    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    src = tmp_path / "document.epub"
    src.write_text("dummy")

    widget._input_path.setText(str(src))
    widget._update_output_path(str(src))
    assert widget._output_path.text().endswith(".epub")

    # PDF formatına geçir / Switch to PDF
    pdf_idx = widget._output_format.findData(".pdf")
    widget._output_format.setCurrentIndex(pdf_idx)
    assert widget._output_path.text().endswith(".pdf")

    # HTML formatına geçir / Switch to HTML
    html_idx = widget._output_format.findData(".html")
    widget._output_format.setCurrentIndex(html_idx)
    assert widget._output_path.text().endswith(".html")

    # DOCX formatına geçir / Switch to DOCX
    docx_idx = widget._output_format.findData(".docx")
    widget._output_format.setCurrentIndex(docx_idx)
    assert widget._output_path.text().endswith(".docx")
