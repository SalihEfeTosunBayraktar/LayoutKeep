"""Widget tests for the progress screen."""

from __future__ import annotations

from layoutkeep.ui.progress import ProgressWidget


def test_set_progress_updates_bar_and_status(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    widget.set_progress(5, 20)

    assert widget._bar.value() == 5
    assert widget._bar.maximum() == 20
    assert "5/20" in widget._status.text()


def test_memory_stats_shown_as_percentage(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)

    widget.set_memory_stats(3, 10)

    assert "3/10" in widget._extra_info.text()
    assert "30%" in widget._extra_info.text()


def test_cancel_button_emits_signal_only_when_running(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)

    assert widget._cancel_btn.isEnabled() is False
    widget.start()
    assert widget._cancel_btn.isEnabled() is True

    with qtbot.waitSignal(widget.cancel_requested, timeout=1000):
        widget._cancel_btn.click()


def test_finish_disables_cancel(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    widget.finish("tamamlandı")

    assert widget._cancel_btn.isEnabled() is False
    assert widget._status.text() == "tamamlandı"


def test_active_segment_updates_the_heading(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    widget.set_active_segment(14, "Bu bir aktif segment metnidir.")

    assert "#14" in widget._preview_title.text()


def test_finished_segments_appear_side_by_side(qtbot):
    """Mockup 09 shows source beside translation, filling in as batches come back.

    The screen used to show one line of the *source* only, which proved the app was busy
    but never that it was producing anything.
    """
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    widget.append_segment_pair("The knotter must be adjusted.", "Bağlayıcı ayarlanmalıdır.")
    widget.append_segment_pair("Tighten the bolts.", "Cıvataları sıkın.")

    source_text = widget._preview_source.toPlainText()
    target_text = widget._preview_target.toPlainText()
    assert "The knotter must be adjusted." in source_text
    assert "Bağlayıcı ayarlanmalıdır." in target_text
    assert "Tighten the bolts." in source_text
    assert "Cıvataları sıkın." in target_text
    # The two panes must stay aligned - a translation without its source is unreadable.
    assert len(source_text.strip().splitlines()) == len(target_text.strip().splitlines())


def test_the_live_view_does_not_grow_without_bound(qtbot):
    """A book is thousands of segments; keeping them all would grow the panes forever."""
    from layoutkeep.ui.progress import _PREVIEW_KEEP

    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()

    for i in range(_PREVIEW_KEEP + 15):
        widget.append_segment_pair(f"source {i}", f"target {i}")

    assert len(widget._preview_pairs) == _PREVIEW_KEEP
    text = widget._preview_source.toPlainText()
    assert "source 0" not in text, "the oldest segment should have been dropped"
    assert f"source {_PREVIEW_KEEP + 14}" in text, "the newest segment must be visible"


def test_starting_a_new_job_clears_the_previous_preview(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start()
    widget.append_segment_pair("old source", "old target")

    widget.start()

    assert widget._preview_source.toPlainText().strip() == ""
    assert widget._preview_target.toPlainText().strip() == ""
    assert widget._preview_pairs == []


def test_progress_detailed_updates_chars_and_eta(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start(total_segments=10, total_chars=1000)

    widget.set_progress_detailed(2, 10, 200, 1000, 25.0, "")

    assert "200" in widget._extra_info.text()
    assert "1,000" in widget._extra_info.text()


def test_set_progress_does_not_feed_fake_chars_to_eta(qtbot):
    # Regresyon: set_progress eskiden record_progress(done, done*50) ile ETA'ya UYDURMA
    # karakter sayısı besliyordu (segment başına 50 kr varsayımı). progress ve
    # progress_detailed birlikte emit edildiğinden ETA'ya iki kez kayıt düşüyor ve hız
    # kirleniyordu. Artık set_progress yalnızca bar/status günceller.
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start(total_segments=10, total_chars=1000)

    widget.set_progress(5, 10)  # tek başına: ETA'ya hiçbir şey yazılmamalı
    assert widget._eta_calc._chars_done == 0
    assert widget._eta_calc._smoothed_rate is None

    # Gerçek akış: detailed sinyali gerçek karakterlerle + ölçülen hızla gelir.
    widget.set_progress(5, 10)
    widget.set_progress_detailed(5, 10, 500, 1000, 50.0, "")
    assert widget._eta_calc._chars_done == 500
    assert widget._eta_calc._smoothed_rate == 50.0


def test_detailed_speed_zero_keeps_previous_rate(qtbot):
    # Ara ilerleme dilimleri (provider içi on_progress) speed=0.0 taşır: batch henüz
    # bitmediği için ölçüm yok. Bu, önceki gerçek hızı bozmamalı.
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start(total_segments=10, total_chars=1000)

    widget.set_progress_detailed(2, 10, 200, 1000, 40.0, "")
    widget.set_progress_detailed(3, 10, 300, 1000, 0.0, "")  # ara dilim
    assert widget._eta_calc._smoothed_rate == 40.0


def test_timer_ticks_elapsed_time(qtbot):
    widget = ProgressWidget()
    qtbot.addWidget(widget)
    widget.start(total_segments=10, total_chars=1000)

    # _on_tick çağrıldığında geçen süre ve kalan süre güncellenmeli
    widget._on_tick()
    assert "Geçen:" in widget._time_info.text()
    assert "Kalan:" in widget._eta.text()

