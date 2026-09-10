"""Tests for DropZoneWidget: drag-and-drop, click browsing, and JobSetupWidget synchronization."""

from __future__ import annotations

from layoutkeep.ui.drop_zone import DropZoneWidget
from layoutkeep.ui.job_setup import JobSetupWidget


def test_drop_zone_set_file_path_and_clear(qtbot, tmp_path):
    widget = DropZoneWidget()
    qtbot.addWidget(widget)

    sample_file = tmp_path / "test.epub"
    sample_file.write_text("dummy epub content")

    received = []
    widget.file_selected.connect(received.append)

    widget.show()
    widget.set_file_path(str(sample_file))
    assert len(received) == 1
    assert received[0] == str(sample_file)
    assert widget._info_title.text() == "test.epub"
    assert not widget._info_container.isHidden()
    assert widget._prompt_label.isHidden()

    widget.clear()
    assert len(received) == 2
    assert received[1] == ""
    assert widget._info_container.isHidden()
    assert not widget._prompt_label.isHidden()


def test_job_setup_and_drop_zone_sync(qtbot, tmp_path):
    setup = JobSetupWidget()
    qtbot.addWidget(setup)

    sample_file = tmp_path / "book.pdf"
    sample_file.write_text("dummy pdf")

    # DropZone'a dosya verildiğinde setup girdisi ve çıktısı güncellenmeli
    setup._drop_zone.set_file_path(str(sample_file))
    assert setup._input_path.text() == str(sample_file)
    assert setup._output_path.text().endswith("book.out.pdf")

    # Çıktı formatı HTML seçilirse çıktı yolu anında güncellenmeli
    idx = setup._output_format.findData(".html")
    setup._output_format.setCurrentIndex(idx)
    assert setup._output_path.text().endswith("book.out.html")
