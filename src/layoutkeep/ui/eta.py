"""Robust and smooth ETA calculator for document translation.

Belge çevirisi için kararlı ve pürüzsüz kalan süre (ETA) hesaplayıcı motoru.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class EtaSnapshot:
    # Anlık hesaplanmış ilerleme ve süre durumu / Current progress and ETA snapshot
    elapsed_seconds: float
    remaining_seconds: float | None
    chars_per_second: float | None
    segments_per_minute: float | None
    percent_done: float
    formatted_elapsed: str
    formatted_remaining: str
    formatted_speed: str


class EtaCalculator:
    """Computes stable, pause-aware, EMA-smoothed translation remaining time.

    Duraklatma sürelerini hesaba katan, soğuk LLM yükleme süresini dengeleyen
    ve üstel hareketli ortalama (EMA) ile kararlı kalan süre hesaplayan motor.
    """

    def __init__(
        self,
        total_segments: int,
        total_chars: int,
        ema_alpha: float = 0.3,
    ) -> None:
        self.total_segments = max(0, total_segments)
        self.total_chars = max(0, total_chars)
        self._ema_alpha = ema_alpha

        self._active_elapsed: float = 0.0
        self._last_tick: float | None = None
        self._is_paused: bool = False

        self._segments_done: int = 0
        self._chars_done: int = 0
        self._cached_segments: int = 0
        self._cached_chars: int = 0

        self._smoothed_rate: float | None = None
        self._batch_count: int = 0

    def start(self) -> None:
        # Zamanlayıcıyı sıfırlayıp başlatır / Resets and starts the timing clock
        now = time.monotonic()
        self._last_tick = now
        self._active_elapsed = 0.0
        self._is_paused = False

    def pause(self) -> None:
        # Zamanlayıcıyı duraklatır / Pauses the timing clock
        if not self._is_paused and self._last_tick is not None:
            self._active_elapsed += time.monotonic() - self._last_tick
            self._last_tick = None
            self._is_paused = True

    def resume(self) -> None:
        # Zamanlayıcıyı devam ettirir / Resumes the timing clock
        if self._is_paused:
            self._last_tick = time.monotonic()
            self._is_paused = False

    def update_elapsed(self) -> float:
        # Aktif çalışma süresini günceller ve döndürür / Updates and returns active elapsed time
        if not self._is_paused and self._last_tick is not None:
            now = time.monotonic()
            self._active_elapsed += now - self._last_tick
            self._last_tick = now
        return self._active_elapsed

    def record_progress(
        self,
        segments_done: int,
        chars_done: int,
        *,
        is_from_memory: bool = False,
        batch_duration_s: float | None = None,
        observed_rate: float | None = None,
    ) -> None:
        # İlerleme adımını kaydeder ve hızı günceller / Records progress and updates speed
        self.update_elapsed()
        prev_chars = self._chars_done
        self._segments_done = min(self.total_segments, segments_done)
        self._chars_done = min(self.total_chars, chars_done) if self.total_chars else chars_done
        added_chars = max(0, self._chars_done - prev_chars)

        if is_from_memory:
            self._cached_segments = self._segments_done
            self._cached_chars = self._chars_done
            return

        self._batch_count += 1
        if observed_rate is not None:
            # Caller-measured batch rate (chars per second), e.g. the worker timing the real
            # provider call. Preferred when available: it is measured over exactly one batch,
            # unlike added_chars / wall-clock which is polluted by other signals' overhead.
            # 0.0 means "no measurement at this point" (mid-batch progress tick) - record the
            # progress but do NOT fall through to the wall-clock guess: a mid-batch tick
            # covers only part of a batch, so chars/wall-clock would be wildly optimistic.
            if observed_rate > 0:
                self._observe_rate(observed_rate)
        elif batch_duration_s is not None and batch_duration_s > 0 and added_chars > 0:
            rate = added_chars / batch_duration_s
            self._observe_rate(rate)
        elif self._smoothed_rate is None and self._active_elapsed > 0:
            net_chars = self._chars_done - self._cached_chars
            if net_chars > 0:
                self._smoothed_rate = net_chars / self._active_elapsed

    def _observe_rate(self, rate: float) -> None:
        # EMA ile hızı günceller / Updates the EMA-smoothed rate
        if self._smoothed_rate is None:
            self._smoothed_rate = rate
        else:
            self._smoothed_rate = (
                self._ema_alpha * rate + (1.0 - self._ema_alpha) * self._smoothed_rate
            )

    def get_remaining_seconds(self) -> float | None:
        # Kalan tahmini süreyi saniye cinsinden hesaplar / Computes remaining seconds
        if self._segments_done >= self.total_segments and self.total_segments > 0:
            return 0.0

        if self._smoothed_rate is not None and self._smoothed_rate > 0.1:
            remaining_chars = max(0, self.total_chars - self._chars_done)
            if remaining_chars == 0 and self.total_segments > self._segments_done:
                avg_chars = (self.total_chars / self.total_segments) if self.total_segments else 50
                remaining_chars = int((self.total_segments - self._segments_done) * avg_chars)
            return max(0.0, remaining_chars / self._smoothed_rate)

        if self._segments_done > 0 and self._active_elapsed > 0:
            sec_per_seg = self._active_elapsed / self._segments_done
            return max(0.0, sec_per_seg * (self.total_segments - self._segments_done))

        return None

    def get_snapshot(self) -> EtaSnapshot:
        # Anlık durumu paketler / Bundles current state into a snapshot
        elapsed = self.update_elapsed()
        remaining = self.get_remaining_seconds()
        rate = self._smoothed_rate
        seg_rate = None
        if rate and self.total_chars and self.total_segments:
            seg_rate = (rate / (self.total_chars / self.total_segments)) * 60

        pct = (self._segments_done / self.total_segments * 100) if self.total_segments else 0.0
        return EtaSnapshot(
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            chars_per_second=rate,
            segments_per_minute=seg_rate,
            percent_done=pct,
            formatted_elapsed=self.format_elapsed(elapsed),
            formatted_remaining=self.format_remaining(remaining),
            formatted_speed=self.format_speed(rate),
        )

    @staticmethod
    def format_elapsed(seconds: float) -> str:
        # Geçen süreyi formatlar / Formats elapsed seconds (MM:SS veya HH:MM:SS)
        s = int(max(0, seconds))
        hrs, remainder = divmod(s, 3600)
        mins, secs = divmod(remainder, 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @staticmethod
    def format_remaining(seconds: float | None) -> str:
        # Kalan süreyi formatlar / Formats remaining time into friendly Turkish
        if seconds is None:
            return "Hesaplanıyor…"
        s = round(seconds)
        if s <= 5:
            return "Tamamlanmak üzere"
        if s < 60:
            return f"~{s} sn kaldı"
        mins, rem_secs = divmod(s, 60)
        if mins < 60:
            return f"~{mins} dk {rem_secs} sn" if rem_secs > 0 else f"~{mins} dk"
        hrs, rem_mins = divmod(mins, 60)
        return f"~{hrs} sa {rem_mins} dk" if rem_mins > 0 else f"~{hrs} sa"

    @staticmethod
    def format_speed(chars_per_sec: float | None) -> str:
        # Çeviri hızını formatlar / Formats translation throughput
        if chars_per_sec is None or chars_per_sec <= 0:
            return "Ölçülüyor…"
        return f"~{chars_per_sec:.1f} kar/sn"
