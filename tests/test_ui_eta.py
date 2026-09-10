"""Unit tests for the EtaCalculator and time formatters."""

from __future__ import annotations

import time

from layoutkeep.ui.eta import EtaCalculator


def test_eta_format_elapsed():
    assert EtaCalculator.format_elapsed(0) == "00:00"
    assert EtaCalculator.format_elapsed(59) == "00:59"
    assert EtaCalculator.format_elapsed(65) == "01:05"
    assert EtaCalculator.format_elapsed(3665) == "01:01:05"


def test_eta_format_remaining():
    assert EtaCalculator.format_remaining(None) == "Hesaplanıyor…"
    assert EtaCalculator.format_remaining(3) == "Tamamlanmak üzere"
    assert EtaCalculator.format_remaining(45) == "~45 sn kaldı"
    assert EtaCalculator.format_remaining(95) == "~1 dk 35 sn"
    assert EtaCalculator.format_remaining(120) == "~2 dk"
    assert EtaCalculator.format_remaining(3660) == "~1 sa 1 dk"


def test_eta_format_speed():
    assert EtaCalculator.format_speed(None) == "Ölçülüyor…"
    assert EtaCalculator.format_speed(0) == "Ölçülüyor…"
    assert EtaCalculator.format_speed(15.42) == "~15.4 kar/sn"


def test_eta_calculator_happy_path():
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()

    snap = calc.get_snapshot()
    assert snap.percent_done == 0.0
    assert snap.formatted_remaining == "Hesaplanıyor…"

    # 2 segment, 200 karakter, 10 saniyede tamamlandı (20 kar/sn)
    calc.record_progress(2, 200, is_from_memory=False, batch_duration_s=10.0)

    snap = calc.get_snapshot()
    assert snap.percent_done == 20.0
    assert snap.chars_per_second == 20.0
    # Kalan 800 karakter / 20 kar/sn = 40 saniye
    assert snap.remaining_seconds is not None
    assert abs(snap.remaining_seconds - 40.0) < 1.0
    assert "~40 sn kaldı" in snap.formatted_remaining


def test_eta_calculator_pause_resume():
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()
    time.sleep(0.05)

    calc.pause()
    paused_elapsed = calc.update_elapsed()
    time.sleep(0.05)
    # Duraklatılmışken süre artmamalı
    assert calc.update_elapsed() == paused_elapsed

    calc.resume()
    time.sleep(0.05)
    assert calc.update_elapsed() > paused_elapsed


def test_eta_calculator_memory_cache_hit_does_not_distort_speed():
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()

    # İlk 5 segment bellekten anında geldi (0 saniye)
    calc.record_progress(5, 500, is_from_memory=True)
    assert calc._smoothed_rate is None

    # Sonraki 1 segment (100 karakter) LLM ile 5 saniyede geldi (20 kar/sn)
    calc.record_progress(6, 600, is_from_memory=False, batch_duration_s=5.0)
    assert calc._smoothed_rate == 20.0
    # Kalan 400 karakter / 20 kar/sn = 20 saniye
    assert abs(calc.get_remaining_seconds() - 20.0) < 1.0


def test_eta_calculator_completion():
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()
    calc.record_progress(10, 1000)
    assert calc.get_remaining_seconds() == 0.0
    assert calc.get_snapshot().percent_done == 100.0


def test_observed_rate_used_verbatim_when_provided():
    # Worker batch süresini ölçüp gerçek hızı verir: chars/elapsed. Bu değer EMA'ya
    # doğrudan işlenir; wall-clock kestirimi (added_chars / geçen süre) kullanılmaz.
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()
    calc.record_progress(2, 200, observed_rate=40.0)
    assert calc._smoothed_rate == 40.0
    snap = calc.get_snapshot()
    # Kalan 800 karakter / 40 kar/sn = 20 saniye
    assert snap.chars_per_second == 40.0
    assert abs(snap.remaining_seconds - 20.0) < 1.0


def test_observed_rate_zero_is_ignored():
    # Ara ilerleme dilimleri speed=0.0 gönderir (o noktada batch bitmedi, ölçüm yok).
    # 0.0 hızı bozmamalı, sonraki gerçek ölçüm ilk değer olmalı.
    calc = EtaCalculator(total_segments=10, total_chars=1000)
    calc.start()
    calc.record_progress(1, 100, observed_rate=0.0)
    assert calc._smoothed_rate is None
    calc.record_progress(3, 300, observed_rate=30.0)
    assert calc._smoothed_rate == 30.0


def test_observed_rate_ema_smooths_across_batches():
    # 20 kar/sn -> 60 kar/sn: EMA(alpha=0.3) 20*0.7 + 60*0.3 = 32
    calc = EtaCalculator(total_segments=10, total_chars=1000, ema_alpha=0.3)
    calc.start()
    calc.record_progress(2, 200, observed_rate=20.0)
    calc.record_progress(4, 400, observed_rate=60.0)
    assert abs(calc._smoothed_rate - 32.0) < 1e-9
