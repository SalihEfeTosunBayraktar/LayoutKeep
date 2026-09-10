"""Metric card widget: icon + label + value, used on the progress screen.

Mockup 09 shows the translation metrics (speed, ETA, segment count, active model) as icon cards
rather than plain text lines. This widget renders one such card. It stays small and
single-responsibility: it only knows how to present a metric with an icon.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.theme import ThemeManager


class MetricCard(QFrame):
    # Tek bir metriği ikon + etiket + değer olarak gösterir / Shows one metric with icon + value

    def __init__(self, icon_name: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._label = QLabel(label)
        self._label.setProperty("class", "muted")
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._value = QLabel("—")
        self._value.setStyleSheet("font-size: 15px; font-weight: 700;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(self._label)
        text_col.addWidget(self._value)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)
        row.addWidget(self._icon)
        row.addLayout(text_col)
        row.addStretch()

        self.apply_theme()

    def apply_theme(self) -> None:
        # İkonu aktif tema aksan rengiyle boyar / Paints icon with the active accent color
        pal = ThemeManager.current_palette()
        self._icon.setPixmap(get_svg_icon(self._icon_name, color=pal.accent, size=20).pixmap(20, 20))

    def set_value(self, text: str) -> None:
        self._value.setText(text if text else "—")

    def set_label(self, text: str) -> None:
        # Dil değişiminde kart etiketini tazeler / Refreshes card label on language change
        self._label.setText(text)
