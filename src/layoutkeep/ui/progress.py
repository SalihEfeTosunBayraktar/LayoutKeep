"""Progress screen: segment counter, real-time ETA, active preview, cancel/pause controls.

Çeviri ilerlemesini, aktif segment önizlemesini, pürüzsüz ETA'yı ve durum kontrollerini sunan modern ekran.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core import tunables
from layoutkeep.ui.eta import EtaCalculator, EtaSnapshot
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.metric_card import MetricCard
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

# ---------------------------------------------------------------------------
# Metin formatlama yardımcıları / Text formatting helpers
# ---------------------------------------------------------------------------


def format_progress_status(done: int, total: int) -> str:
    """İlerleme çubuğu yanındaki durum satırını formatlar / Formats status line."""
    pct = (done / total * 100) if total else 0.0
    return f"{done}/{total} segment çevrildi (%{pct:.1f})"


def format_memory_stats_text(hits: int, total: int) -> str:
    """TM isabet oranını yüzde olarak formatlar / Formats TM hit rate as a percent."""
    rate = hits / total if total else 0.0
    return f"TM isabet: {hits}/{total} ({rate:.0%})"


def format_batch_timeout_text(seconds: float) -> str:
    """Batch üst sınır metnini formatlar / Formats batch upper-bound text."""
    return f"Beklenen üst sınır: {seconds:.0f}s"


def format_chars_label_text(done_chars: int, total_chars: int) -> str:
    """Karakter sayacı etiketini formatlar / Formats characters counter label."""
    return f"{UIStrings.PROGRESS_CHARS_LABEL} {done_chars:,} / {total_chars:,}"


def format_elapsed_label(snap: EtaSnapshot) -> str:
    """Geçen süre etiketini formatlar / Formats elapsed-time label."""
    return f"{UIStrings.PROGRESS_ELAPSED} {snap.formatted_elapsed}"


def format_remaining_label(snap: EtaSnapshot) -> str:
    """Kalan süre etiketini formatlar / Formats remaining-time label."""
    return f"{UIStrings.PROGRESS_REMAINING} {snap.formatted_remaining}"


def format_speed_label(snap: EtaSnapshot) -> str | None:
    """Hız etiketini formatlar; hız ölçülmediyse None / Formats speed label or None."""
    if not snap.chars_per_second:
        return None
    return f"{UIStrings.PROGRESS_SPEED} {snap.formatted_speed}"


def apply_pause_button_state(button: QPushButton, is_paused: bool) -> None:
    """Duraklat/devam butonunun görünümünü duruma göre ayarlar / Applies pause-state visuals."""
    button.setText(UIStrings.RESUME_BTN if is_paused else UIStrings.PAUSE_BTN)
    icon_name = "play" if is_paused else "pause"
    button.setIcon(get_svg_icon(icon_name, size=16))


# ---------------------------------------------------------------------------
# Görsel katman kurma yardımcısı / Visual layer builder
# ---------------------------------------------------------------------------


#: How many finished segments the live view keeps. A long book would otherwise grow the
#: panes without bound for text nobody scrolls back to.
_PREVIEW_KEEP = 40


def _build_preview_pane() -> QTextEdit:
    # Salt okunur, kaydirilabilir onizleme paneli / Read-only scrollable preview pane
    pane = QTextEdit()
    pane.setReadOnly(True)
    pane.setMinimumHeight(132)
    pane.setStyleSheet("font-size: 12px; padding: 4px;")
    pane.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return pane


class ProgressCardLayout:
    """Progress kartının görsel düzenini kurar / Builds the progress card visual layout.

    ProgressWidget üzerindeki widget referanslarını parametre olarak alır ve
    dış kısımdaki QFrame'i (kartı) inşa eder. Tek sorumluluğu Qt düzeni kurmaktır.
    """

    def __init__(self, panel: ProgressWidget) -> None:
        self._panel = panel

    def build_card(self) -> QFrame:
        """Ana kart çerçevesini oluşturur / Builds the main card frame."""
        card_layout = QVBoxLayout()
        card_layout.addLayout(self._build_top_row())
        card_layout.addWidget(self._panel._status)
        card_layout.addWidget(self._panel._bar)
        # Mock-up 09 puts the four figures in one row directly under the bar, with the live
        # text below them. Stacking them underneath in a 2x2 grid left the card looking
        # scattered at the width the window actually opens at.
        card_layout.addLayout(self._build_stats_grid())
        card_layout.addWidget(self._build_preview_card(), 1)

        card = QFrame()
        card.setProperty("class", "card")
        card.setLayout(card_layout)
        card.setMaximumWidth(860)
        return card

    def build_main_layout(self, card: QFrame) -> None:
        """Panelin ana düzenini kurar / Assembles the panel's main layout."""
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._panel._pause_btn)
        btn_row.addWidget(self._panel._cancel_btn)
        btn_row.addStretch()

        center_col = QVBoxLayout()
        center_col.addWidget(card)
        center_col.addSpacing(8)
        center_col.addLayout(btn_row)

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addLayout(center_col)
        center_row.addStretch()

        main_layout = QVBoxLayout(self._panel)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.addStretch()
        main_layout.addLayout(center_row)
        main_layout.addStretch()

    # ----- Dahili inşa adımları / Internal build steps -----

    def _build_top_row(self) -> QHBoxLayout:
        top_row = QHBoxLayout()
        top_row.addWidget(self._panel._title)
        top_row.addStretch()
        top_row.addWidget(self._panel._time_info)
        top_row.addSpacing(12)
        top_row.addWidget(self._panel._eta)
        return top_row

    def _build_stats_grid(self) -> QGridLayout:
        # Metrik kartlarını 2x2 ızgara halinde kurar / Lays metric cards out in a 2x2 grid
        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 4, 0, 4)
        stats_grid.setSpacing(8)
        stats_grid.addWidget(self._panel._speed_card, 0, 0)
        stats_grid.addWidget(self._panel._eta_card, 0, 1)
        stats_grid.addWidget(self._panel._segments_card, 0, 2)
        stats_grid.addWidget(self._panel._model_card, 0, 3)
        stats_grid.addWidget(self._panel._extra_info, 1, 0, 1, 4)
        stats_grid.addWidget(self._panel._flags_label, 2, 0, 1, 4)
        return stats_grid

    def _build_preview_card(self) -> QFrame:
        preview_card = QFrame()
        preview_card.setProperty("class", "card")
        preview_card.setStyleSheet("border-radius: 6px; padding: 6px;")
        pv_layout = QVBoxLayout(preview_card)
        pv_layout.setContentsMargins(8, 6, 8, 6)
        pv_layout.addWidget(self._panel._preview_title)

        heads = QHBoxLayout()
        heads.setSpacing(10)
        heads.addWidget(self._panel._preview_source_head, 1)
        heads.addWidget(self._panel._preview_target_head, 1)
        pv_layout.addLayout(heads)

        panes = QHBoxLayout()
        panes.setSpacing(10)
        panes.addWidget(self._panel._preview_source, 1)
        panes.addWidget(self._panel._preview_target, 1)
        pv_layout.addLayout(panes)
        return preview_card


# ---------------------------------------------------------------------------
# Ana widget / Main widget
# ---------------------------------------------------------------------------


class ProgressWidget(QWidget):
    # Çeviri sürecini gerçek zamanlı gösteren zenginleştirilmiş bileşen / Translation progress widget
    cancel_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_paused = False
        self._eta_calc = EtaCalculator(total_segments=0, total_chars=0)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._on_tick)

        self._init_controls()
        layout_builder = ProgressCardLayout(self)
        layout_builder.build_main_layout(layout_builder.build_card())
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        self._pause_btn.clicked.connect(self._toggle_pause)

    def _init_controls(self) -> None:
        # Arayüz kontrollerini başlatır / Initializes UI controls
        self._title = QLabel(UIStrings.PROGRESS_TITLE)
        self._title.setStyleSheet("font-size: 16px; font-weight: 700;")

        self._status = QLabel("hazır")
        self._status.setStyleSheet("font-size: 13px; font-weight: 500;")

        self._time_info = QLabel("")
        self._time_info.setProperty("class", "muted")

        self._eta = QLabel("")
        self._eta.setProperty("class", "secondary")

        self._bar = QProgressBar()
        self._bar.setTextVisible(True)

        # Metrik kartları (mockup 09): hız, kalan süre, segmentler, aktif model
        self._speed_card = MetricCard("gauge", UIStrings.PROGRESS_SPEED)
        self._eta_card = MetricCard("hourglass", UIStrings.PROGRESS_REMAINING)
        self._segments_card = MetricCard("layers", UIStrings.PROGRESS_SEGMENTS_LABEL)
        self._model_card = MetricCard("cpu", UIStrings.PROGRESS_MODEL_LABEL)

        # TM tasarrufu / batch üst sınırı gibi ikincil metinler
        self._extra_info = QLabel("")
        self._extra_info.setProperty("class", "muted")

        self._flags_label = QLabel("")
        self._flags_label.setProperty("class", "muted")
        self._flags_label.setVisible(False)

        self._preview_title = QLabel(UIStrings.PROGRESS_ACTIVE_TITLE)
        self._preview_title.setStyleSheet("font-size: 11px; font-weight: 600;")
        self._preview_title.setProperty("class", "muted")

        # Mockup 09 shows the document being translated as two columns, source beside
        # translation, filling in as batches come back. A single line of the *source* - which
        # is what this used to be - showed the app was busy but never that it was working.
        self._preview_source = _build_preview_pane()
        self._preview_target = _build_preview_pane()
        self._preview_source_head = QLabel(UIStrings.PROGRESS_PREVIEW_SOURCE)
        self._preview_target_head = QLabel(UIStrings.PROGRESS_PREVIEW_TARGET)
        for head in (self._preview_source_head, self._preview_target_head):
            head.setProperty("class", "muted")
            head.setStyleSheet("font-size: 11px; font-weight: 600;")
        #: Kept so the panes can be capped without re-reading the widgets.
        self._preview_pairs: list[tuple[str, str]] = []

        self._init_buttons()

    def _init_buttons(self) -> None:
        # Eylem butonlarını kurar / Sets up action buttons
        self._pause_btn = QPushButton(UIStrings.PAUSE_BTN)
        self._pause_btn.setIcon(get_svg_icon("pause", size=16))
        self._pause_btn.setEnabled(False)

        self._cancel_btn = QPushButton(UIStrings.CANCEL_BTN)
        self._cancel_btn.setEnabled(False)
        self._apply_theme_buttons()

    def _apply_theme_buttons(self) -> None:
        # İkon renklerini aktif temaya göre ayarlar / Colors icons for the active theme
        pal = ThemeManager.current_palette()
        self._pause_btn.setIcon(get_svg_icon("pause", color=pal.text_primary, size=16))
        self._cancel_btn.setIcon(get_svg_icon("close", color=pal.error, size=16))

    def apply_theme(self) -> None:
        # Tema değişiminde buton ikonlarını tazeler / Refreshes button icons on theme change
        self._apply_theme_buttons()

    def _toggle_pause(self) -> None:
        # Duraklatma ve devam etme durumunu yönetir / Manages pause and resume toggle
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._eta_calc.pause()
            self.pause_requested.emit()
        else:
            self._eta_calc.resume()
            self.resume_requested.emit()
        apply_pause_button_state(self._pause_btn, self._is_paused)

    def _on_tick(self) -> None:
        # Canlı zamanlayıcı adımı / Live timer tick
        if self._is_paused:
            return
        snap = self._eta_calc.get_snapshot()
        self._time_info.setText(format_elapsed_label(snap))
        self._eta.setText(format_remaining_label(snap))
        self._eta_card.set_value(snap.formatted_remaining)
        speed_text = format_speed_label(snap)
        if speed_text is not None:
            self._speed_card.set_value(speed_text)

    def start(self, total_segments: int = 0, total_chars: int = 0) -> None:
        # İlerlemeyi sıfırlar ve zamanlayıcıyı başlatır / Resets progress and starts timer
        self._is_paused = False
        self._eta_calc = EtaCalculator(total_segments, total_chars)
        self._eta_calc.start()
        self._timer.start()

        self._bar.setValue(0)
        self._status.setText(UIStrings.PROGRESS_STARTING)
        self._time_info.setText(f"{UIStrings.PROGRESS_ELAPSED} 00:00")
        self._eta.setText(f"{UIStrings.PROGRESS_REMAINING} Hesaplanıyor…")
        self._segments_card.set_value(f"0 / {total_segments}" if total_segments else "0 / ?")
        self._model_card.set_value("—")
        self._extra_info.setText("")
        self._flags_label.setVisible(False)
        self._flags_label.setText("")
        self._preview_pairs.clear()
        self._preview_source.clear()
        self._preview_target.clear()
        self._pause_btn.setText(UIStrings.PAUSE_BTN)
        self._pause_btn.setIcon(get_svg_icon("pause", size=16))
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_review_flags(self, flagged: int, done: int) -> None:
        """Show how many segments have been flagged so far.

        The figures used to arrive only on the completion screen, so a run going badly looked
        exactly like a good one until it finished - there was nothing to decide on before
        spending the whole wait.
        """
        self._flags_label.setVisible(bool(flagged))
        if flagged:
            self._flags_label.setText(UIStrings.PROGRESS_FLAGS.format(count=flagged))

    def set_active_segment(self, index: int, preview: str) -> None:
        # Aktif işlenen segmentin başlığını günceller / Updates the active segment heading
        self._preview_title.setText(f"{UIStrings.PROGRESS_ACTIVE_TITLE} #{index}")

    def append_segment_pair(self, source: str, target: str) -> None:
        """Add one finished segment to the live side-by-side view."""
        self._preview_pairs.append((source, target))
        keep = tunables.get("preview.keep_segments")
        if len(self._preview_pairs) > keep:
            del self._preview_pairs[: len(self._preview_pairs) - keep]
            self._preview_source.clear()
            self._preview_target.clear()
            for src_text, tgt_text in self._preview_pairs:
                self._preview_source.append(src_text)
                self._preview_target.append(tgt_text)
        else:
            self._preview_source.append(source)
            self._preview_target.append(target)
        for pane in (self._preview_source, self._preview_target):
            pane.verticalScrollBar().setValue(pane.verticalScrollBar().maximum())

    def set_progress(self, done: int, total: int) -> None:
        # İlerleme çubuğunu ve durumunu günceller / Updates progress bar and status
        self._bar.setMaximum(total)
        self._bar.setValue(done)
        self._status.setText(format_progress_status(done, total))
        self._segments_card.set_value(f"{done} / {total}")
        if self._eta_calc.total_segments == 0 and total > 0:
            self._eta_calc.total_segments = total
        # NOT: ETA burada beslenmez - set_progress_detailed gerçek karakter sayısıyla besler
        # (önceden done*50 sahte değeri ETA'yı kirletiyor ve çift kayıt oluşturuyordu).
        self._on_tick()

    def set_progress_detailed(
        self, done_seg: int, total_seg: int, done_chars: int, total_chars: int, speed: float, eta_str: str
    ) -> None:
        # Detaylı ilerleme ve karakter sayaçlarını günceller / Updates detailed progress
        if total_chars > 0:
            self._extra_info.setText(format_chars_label_text(done_chars, total_chars))
            self._eta_calc.total_chars = total_chars
        if total_seg > 0:
            self._eta_calc.total_segments = total_seg
        # Worker batch süresini ölçüp gerçek hızı (karakter/sn) speed olarak gönderir;
        # EtaCalculator bunu EMA ile işler. 0.0 = bu dilimde ölçüm yok (ara ilerleme).
        self._eta_calc.record_progress(done_seg, done_chars, observed_rate=speed)
        self._on_tick()

    def set_model_name(self, name: str) -> None:
        # Aktif modelin adını metrik kartında gösterir / Shows active model name on the metric card
        self._model_card.set_value(name or "—")

    def set_memory_stats(self, hits: int, total: int) -> None:
        self._extra_info.setText(format_memory_stats_text(hits, total))

    def set_batch_timeout(self, seconds: float) -> None:
        self._extra_info.setText(format_batch_timeout_text(seconds))

    def finish(self, message: str) -> None:
        self._timer.stop()
        self._status.setText(message)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)

    def retranslate_ui(self) -> None:
        # Arayüz diline göre metinleri günceller / Updates texts for active language
        self._title.setText(UIStrings.PROGRESS_TITLE)
        self._pause_btn.setText(UIStrings.RESUME_BTN if self._is_paused else UIStrings.PAUSE_BTN)
        self._cancel_btn.setText(UIStrings.CANCEL_BTN)
        self._preview_title.setText(UIStrings.PROGRESS_ACTIVE_TITLE)
        self._speed_card.set_label(UIStrings.PROGRESS_SPEED)
        self._eta_card.set_label(UIStrings.PROGRESS_REMAINING)
        self._segments_card.set_label(UIStrings.PROGRESS_SEGMENTS_LABEL)
        self._model_card.set_label(UIStrings.PROGRESS_MODEL_LABEL)
