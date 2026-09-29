"""İlerleme kartının kontrollerini kurar / Builds the progress card's controls.

Başlık, durum satırı, ilerleme çubuğu, dört metrik kartı, ikincil metinler, canlı önizleme
bölmeleri ve eylem düğmeleri. Panelin widget referansları üzerine yazar; tek sorumluluğu
kontrolleri kurmak ve düğme ikonlarını temaya göre tazelemektir (ProgressCardLayout ile aynı
desen: metin ve renk kararları panelde kalır).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QTextEdit

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.metric_card import MetricCard
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

if TYPE_CHECKING:  # yalnız tip için / annotation only: the panel imports this module
    from layoutkeep.ui.progress import ProgressWidget


def build_preview_pane() -> QTextEdit:
    # Salt okunur, kaydirilabilir onizleme paneli / Read-only scrollable preview pane
    pane = QTextEdit()
    pane.setReadOnly(True)
    pane.setMinimumHeight(76)
    pane.setStyleSheet("font-size: 12px; padding: 4px;")
    pane.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return pane


class ProgressControlsBuilder:
    """Kontrolleri ve eylem düğmelerini panele kurar / Builds the controls and buttons."""

    def __init__(self, panel: ProgressWidget) -> None:
        self._panel = panel

    def build(self) -> None:
        # Arayüz kontrollerini başlatır / Initializes UI controls
        panel = self._panel
        panel._title = QLabel(UIStrings.PROGRESS_TITLE)
        panel._title.setStyleSheet("font-size: 16px; font-weight: 700;")

        panel._status = QLabel(UIStrings.STATUS_READY)
        panel._status.setStyleSheet("font-size: 13px; font-weight: 500;")

        panel._time_info = QLabel("")
        panel._time_info.setProperty("class", "muted")

        panel._eta = QLabel("")
        panel._eta.setProperty("class", "secondary")

        panel._bar = QProgressBar()
        panel._bar.setTextVisible(True)

        # Metrik kartları (mockup 09): hız, kalan süre, segmentler, aktif model
        panel._speed_card = MetricCard("gauge", UIStrings.PROGRESS_SPEED)
        panel._eta_card = MetricCard("hourglass", UIStrings.PROGRESS_REMAINING)
        panel._segments_card = MetricCard("layers", UIStrings.PROGRESS_SEGMENTS_LABEL)
        panel._model_card = MetricCard("cpu", UIStrings.PROGRESS_MODEL_LABEL)

        # TM tasarrufu / batch üst sınırı gibi ikincil metinler
        panel._extra_info = QLabel("")
        panel._extra_info.setProperty("class", "muted")

        from layoutkeep.ui.activity_feed import ActivityFeed

        panel._feed = ActivityFeed()
        panel._flags_label = QLabel("")
        panel._flags_label.setProperty("class", "muted")
        panel._flags_label.setVisible(False)

        panel._preview_title = QLabel(UIStrings.PROGRESS_ACTIVE_TITLE)
        panel._preview_title.setStyleSheet("font-size: 11px; font-weight: 600;")
        panel._preview_title.setProperty("class", "muted")

        # Mockup 09 shows the document being translated as two columns, source beside
        # translation, filling in as batches come back. A single line of the *source* - which
        # is what this used to be - showed the app was busy but never that it was working.
        panel._preview_source = build_preview_pane()
        panel._preview_target = build_preview_pane()
        panel._preview_source_head = QLabel(UIStrings.PROGRESS_PREVIEW_SOURCE)
        panel._preview_target_head = QLabel(UIStrings.PROGRESS_PREVIEW_TARGET)
        for head in (panel._preview_source_head, panel._preview_target_head):
            head.setProperty("class", "muted")
            head.setStyleSheet("font-size: 11px; font-weight: 600;")
        #: Kept so the panes can be capped without re-reading the widgets.
        panel._preview_pairs: list[tuple[str, str]] = []

        self._build_buttons()

    def _build_buttons(self) -> None:
        # Eylem butonlarını kurar / Sets up action buttons
        panel = self._panel
        panel._pause_btn = QPushButton(UIStrings.PAUSE_BTN)
        panel._pause_btn.setIcon(get_svg_icon("pause", size=16))
        panel._pause_btn.setEnabled(False)

        panel._cancel_btn = QPushButton(UIStrings.CANCEL_BTN)
        panel._cancel_btn.setEnabled(False)
        self.apply_theme()

    def apply_theme(self) -> None:
        # İkon renklerini aktif temaya göre ayarlar / Colors icons for the active theme
        panel = self._panel
        pal = ThemeManager.current_palette()
        panel._pause_btn.setIcon(get_svg_icon("pause", color=pal.text_primary, size=16))
        panel._cancel_btn.setIcon(get_svg_icon("close", color=pal.error, size=16))
