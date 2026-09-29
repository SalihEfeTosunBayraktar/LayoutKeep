"""Yüzen çubuğun kartını kurar / Builds the floating bar's card.

FloatingProgress'in widget referanslarını panelden alır ve kartı, satırları ve düğmeleri kurar.
Tek sorumluluğu Qt düzeni kurmaktır; renk, metin ve görünürlük kararları panele aittir
(ProgressCardLayout ile aynı desen).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:  # yalnız tip için / annotation only: the panel imports this module
    from layoutkeep.ui.floating_progress import FloatingProgress


class FloatingCardLayout:
    """Kartı, satırları ve düğmeleri kurar / Builds the card, its rows and its buttons."""

    def __init__(self, panel: FloatingProgress) -> None:
        self._panel = panel

    def build(self) -> None:
        panel = self._panel
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        panel._card = QFrame()
        panel._card.setObjectName("floatCard")
        outer.addWidget(panel._card)

        rows = QVBoxLayout(panel._card)
        panel._rows = rows
        rows.setContentsMargins(14, 10, 14, 10)
        rows.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        panel._title = QLabel()
        panel._title.setObjectName("floatTitle")
        panel._percent = QLabel("0%")
        panel._percent.setObjectName("floatPercent")
        panel._percent.setCursor(Qt.CursorShape.OpenHandCursor)
        top.addWidget(panel._title, 1)
        top.addWidget(panel._percent, 0, Qt.AlignmentFlag.AlignRight)
        rows.addLayout(top)

        panel._detail = QLabel()
        panel._detail.setObjectName("floatDetail")
        rows.addWidget(panel._detail)

        panel._bar = QProgressBar()
        panel._bar.setObjectName("floatBar")
        panel._bar.setTextVisible(False)
        panel._bar.setFixedHeight(8)
        panel._bar.setRange(0, 1)
        panel._bar.setValue(0)
        rows.addWidget(panel._bar)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        panel._pause_button = QPushButton()
        panel._pause_button.setObjectName("floatGhost")
        panel._pause_button.clicked.connect(panel._on_pause)
        panel._restore_button = QPushButton()
        panel._restore_button.setObjectName("floatPrimary")
        panel._restore_button.clicked.connect(panel.restore_requested.emit)
        panel._output_button = QPushButton()
        panel._output_button.setObjectName("floatSuccess")
        panel._output_button.clicked.connect(panel.open_output_requested.emit)
        panel._new_button = QPushButton()
        panel._new_button.setObjectName("floatGhost")
        panel._new_button.clicked.connect(panel.new_job_requested.emit)
        panel._fold_button = QPushButton()
        panel._fold_button.setObjectName("floatGhost")
        panel._fold_button.clicked.connect(panel.toggle_folded)
        buttons.addWidget(panel._pause_button)
        buttons.addStretch(1)
        buttons.addWidget(panel._output_button)
        buttons.addWidget(panel._new_button)
        buttons.addWidget(panel._restore_button)
        buttons.addWidget(panel._fold_button)
        rows.addLayout(buttons)
