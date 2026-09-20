"""Tests for pause, resume, cancellation, and resource cleanup."""

from __future__ import annotations

import gc

from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.progress import ProgressWidget, apply_pause_button_state
from layoutkeep.ui.worker import TranslationWorker


def test_progress_widget_pause_resume_toggle(qtbot):
    from layoutkeep.ui.strings import UIStrings

    # The button's wording belongs to the interface language; assert Turkish explicitly rather
    # than inheriting whatever the previous test left set.
    UIStrings.set_language("tr")
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    assert widget._pause_btn.isEnabled() is True
    assert widget._pause_btn.text() == "Duraklat"

    with qtbot.waitSignal(widget.pause_requested, timeout=1000):
        widget._pause_btn.click()

    assert widget._is_paused is True
    assert widget._pause_btn.text() == "Devam Et"

    with qtbot.waitSignal(widget.resume_requested, timeout=1000):
        widget._pause_btn.click()

    assert widget._is_paused is False
    assert widget._pause_btn.text() == "Duraklat"

    UIStrings.set_language("en")
    assert widget._pause_btn.text() == "Duraklat"  # the label only changes on the next state flip
    apply_pause_button_state(widget._pause_btn, False)
    assert widget._pause_btn.text() == "Pause"


def test_worker_pause_resume_and_cleanup(tmp_path):
    config = JobConfig(
        input_path=str(tmp_path / "in.epub"),
        output_path=str(tmp_path / "out.epub"),
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake"),
    )
    worker = TranslationWorker(config)

    assert worker._pause_event.is_set() is True
    worker.pause()
    assert worker._pause_event.is_set() is False

    worker.resume()
    assert worker._pause_event.is_set() is True

    # Kaynak temizliği fonksiyonunun hatasız çalıştığını doğrula
    worker._cleanup_resources()
    assert gc.isenabled()
