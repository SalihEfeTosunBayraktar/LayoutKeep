"""Translation-finished screen: open the result, show it in a folder, start another job.

3. adım: çeviri tamamlandıktan sonra gösterilen ekran. Kullanıcıya üç yol sunar:
çıktı dosyasını sistemin varsayılan uygulamasında açmak, klasörde göstermek veya
yeni bir çeviri başlatmak. Gözden geçirme editörü kaldırıldığı için (bkz. main_window)
bu ekran, işin bitmiş çıktısına ulaşmanın tek ve basit yoludur.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager


def open_output(output_path: str, parent: QWidget | None) -> None:
    """Open the produced translation in the system's default app."""
    path = Path(output_path) if output_path else None
    if path is None or not path.exists():
        QMessageBox.warning(
            parent, UIStrings.OPEN_OUTPUT_BTN, f"{UIStrings.OUTPUT_MISSING} {output_path}"
        )
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))


def show_output_in_folder(output_path: str, parent: QWidget | None) -> None:
    """Open the folder holding the produced translation."""
    path = Path(output_path) if output_path else None
    if path is None or not path.exists():
        QMessageBox.warning(
            parent,
            UIStrings.SHOW_IN_FOLDER_BTN,
            f"{UIStrings.OUTPUT_MISSING} {output_path}",
        )
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve().parent)))


def format_duration(seconds: float) -> str:
    """`02 dk 18 sn` in the mockup; minutes and seconds, no false precision."""
    total = max(0, round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class CompletionWidget(QFrame):
    """Shown after a job finishes; offers open/folder/new-translation actions.

    Yeni çeviri istendiğinde `back_to_setup_requested` sinyali yayılır; ana pencere
    kurulum ekranına döner. Çıktı dosyası `set_output_path` ile bildirilir ve mevcut
    değilse aç/klasör butonları devre dışı kalır.
    """

    #: The user wants to start another job.
    back_to_setup_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._output_path = ""
        self._stats: dict = {}
        self._init_ui()

    def _init_ui(self) -> None:
        # Başarı kartını ve eylem butonlarını kurar / Builds the success card
        self.setObjectName("completionCard")
        self.setProperty("class", "card")

        self._title = QLabel(UIStrings.COMPLETION_TITLE)
        self._title.setStyleSheet("font-size: 20px; font-weight: 800;")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle = QLabel(UIStrings.COMPLETION_SUBTITLE)
        self._subtitle.setProperty("class", "muted")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)

        self._output_label = QLabel("")
        self._output_label.setProperty("class", "secondary")
        self._output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._output_label.setWordWrap(True)

        # Mockup 10 reports what the run did. Until now the screen said only where the file
        # went, so a job that flagged half its segments looked identical to a clean one.
        self._stats_title = QLabel(UIStrings.COMPLETION_STATS_TITLE)
        self._stats_title.setProperty("class", "muted")
        self._stats_title.setStyleSheet("font-size: 11px; font-weight: 600;")
        self._stats_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats_title.setVisible(False)

        self._stats_label = QLabel("")
        self._stats_label.setProperty("class", "secondary")
        self._stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats_label.setWordWrap(True)
        self._stats_label.setVisible(False)

        self._open_btn = QPushButton(UIStrings.OPEN_OUTPUT_BTN)
        self._open_btn.setMinimumHeight(36)
        self._open_btn.setEnabled(False)
        self._open_btn.setProperty("class", "primary")
        self._open_btn.clicked.connect(lambda: open_output(self._output_path, self))

        self._folder_btn = QPushButton(UIStrings.SHOW_IN_FOLDER_BTN)
        self._folder_btn.setMinimumHeight(36)
        self._folder_btn.setEnabled(False)
        self._folder_btn.clicked.connect(lambda: show_output_in_folder(self._output_path, self))

        self._new_btn = QPushButton(UIStrings.BACK_TO_SETUP_BTN)
        self._new_btn.setMinimumHeight(36)
        self._new_btn.setProperty("class", "primary")
        self._new_btn.clicked.connect(self.back_to_setup_requested.emit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        btn_row.addWidget(self._open_btn)
        btn_row.addWidget(self._folder_btn)
        btn_row.addWidget(self._new_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)
        layout.addStretch()
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addSpacing(8)
        layout.addWidget(self._output_label)
        layout.addSpacing(10)
        layout.addWidget(self._stats_title)
        layout.addWidget(self._stats_label)
        layout.addSpacing(12)
        layout.addLayout(btn_row)
        layout.addStretch()

        self.apply_theme()

    def set_output_path(self, path: str | None) -> None:
        """Show the produced file and enable open/folder actions when it exists."""
        self._output_path = path or ""
        exists = bool(self._output_path) and Path(self._output_path).exists()
        self._open_btn.setEnabled(exists)
        self._folder_btn.setEnabled(exists)
        if exists:
            self._output_label.setText(f"{UIStrings.OUTPUT_READY} {Path(self._output_path).name}")
            self._output_label.setToolTip(self._output_path)
        else:
            self._output_label.setText("")
            self._output_label.setToolTip("")

    def set_stats(self, stats: dict | None) -> None:
        """Show the job's figures. Everything here is counted, nothing is estimated."""
        self._stats = dict(stats) if stats else {}
        if not self._stats:
            self._stats_title.setVisible(False)
            self._stats_label.setVisible(False)
            return

        total = int(self._stats.get("segments_total", 0))
        done = int(self._stats.get("segments_done", 0))
        flagged = int(self._stats.get("segments_flagged", 0))
        pct = round(done / total * 100) if total else 0
        lines = [
            UIStrings.COMPLETION_SEGMENTS.format(done=done, total=total, pct=pct),
            UIStrings.COMPLETION_SPEED.format(
                speed=round(float(self._stats.get("chars_per_second", 0.0)))
            ),
            UIStrings.COMPLETION_FIDELITY.format(
                pct=round(float(self._stats.get("clean_ratio", 0.0)) * 100, 1)
            ),
            UIStrings.COMPLETION_DURATION.format(
                duration=format_duration(float(self._stats.get("elapsed_s", 0.0)))
            ),
        ]
        if flagged:
            lines.append(UIStrings.COMPLETION_FLAGGED.format(count=flagged))
        self._stats_label.setText("\n".join(lines))
        self._stats_title.setVisible(True)
        self._stats_label.setVisible(True)

    def apply_theme(self) -> None:
        # Tema değişiminde ikon renklerini günceller / Refreshes icon colors on theme change
        pal = ThemeManager.current_palette()
        self._open_btn.setIcon(get_svg_icon("external_link", color=pal.accent_text, size=16))
        self._folder_btn.setIcon(get_svg_icon("folder", color=pal.text_muted, size=16))
        self._new_btn.setIcon(get_svg_icon("arrow_left", color=pal.accent_text, size=16))

    def retranslate_ui(self) -> None:
        # Arayüz diline göre metinleri günceller / Updates texts for active language
        self._title.setText(UIStrings.COMPLETION_TITLE)
        self._subtitle.setText(UIStrings.COMPLETION_SUBTITLE)
        self._stats_title.setText(UIStrings.COMPLETION_STATS_TITLE)
        # Rebuild the figures in the new language rather than leaving the old sentences.
        self.set_stats(self._stats)
        self._open_btn.setText(UIStrings.OPEN_OUTPUT_BTN)
        self._folder_btn.setText(UIStrings.SHOW_IN_FOLDER_BTN)
        self._new_btn.setText(UIStrings.BACK_TO_SETUP_BTN)
        # Çıktı etiketi dosya adı içeriyor olabilir; yolu koruyarak yeniden doldur.
        if self._output_path:
            self.set_output_path(self._output_path)
