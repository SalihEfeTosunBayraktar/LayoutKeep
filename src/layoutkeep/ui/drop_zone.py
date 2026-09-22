"""Drop zone widget: unified click-to-browse and drag-and-drop file selector.

Hem tıklayarak dosya seçmeyi hem de sürükle-bırak yöntemini tek bir modern alanda birleştiren dosya seçici.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager


def _format_size(bytes_count: int) -> str:
    # Bayt miktarını okunabilir boyuta çevirir / Formats bytes to readable size
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / (1024 * 1024):.1f} MB"


class DropZoneWidget(QFrame):
    # Birleşik sürükle-bırak ve tıklama destekli dosya alanı / Unified drag-drop and click file area
    file_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(UIStrings.DROPZONE_PROMPT)

        self._current_path: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        # Arayüz bileşenlerini kurar / Initializes UI elements
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(30, 30)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_icon()

        self._prompt_label = QLabel(UIStrings.DROPZONE_PROMPT)


        self._prompt_label.setWordWrap(True)
        self._prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prompt_label.setStyleSheet("font-weight: 600; font-size: 13px;")

        self._hint_label = QLabel(UIStrings.DROPZONE_HINT)
        self._hint_label.setWordWrap(True)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setProperty("class", "muted")

        self._browse_btn = QPushButton(UIStrings.BROWSE_BTN)
        self._browse_btn.setProperty("class", "primary")
        self._browse_btn.setIcon(
            get_svg_icon("folder", color=ThemeManager.current_palette().accent_text, size=16)
        )
        self._browse_btn.clicked.connect(self._browse)

        self._info_container = self._build_info_container()

        # Texts on the left, the button on the right: one row instead of a stack of four centred
        # rows. The reader asked for this, and it is also what makes the zone short enough to sit
        # above the settings card without pushing it off screen.
        self._prompt_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._hint_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(1)
        texts.addWidget(self._prompt_label)
        texts.addWidget(self._hint_label)

        # The two lines live in their own widget, and they do NOT wrap. A word-wrapped QLabel caps
        # the height a layout will take from it at the text's own height, so the row sized itself
        # to 20px, sat centred in the 68px box and left the button hanging out of it - the
        # misalignment the reader kept seeing. Without wrapping the labels report a normal height
        # and the row fills the box. The window's width is computed from these labels, so a longer
        # language makes the window wider instead of clipping the line.
        self._prompt_label.setWordWrap(False)
        self._hint_label.setWordWrap(False)
        text_holder = QWidget()
        text_holder.setLayout(texts)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(12)
        # No per-item alignment: Qt leaves an aligned item out of the row's height calculation, so
        # the layout sized itself to the text lines alone (32px), centred at y=18, and the button
        # hung out of it - which is exactly the misalignment the reader saw. A plain row centres
        # everything on its own.
        layout.addWidget(self._icon_label)
        layout.addWidget(text_holder, 1)
        layout.addWidget(self._browse_btn)
        layout.addWidget(self._info_container)
        # One row, so the cap can be far lower than the stacked version needed.
        self.setMaximumHeight(68)

    def _set_icon(self) -> None:
        # Yükleme ikonunu aktif temaya göre boyar / Paints the upload icon for the theme
        pal = ThemeManager.current_palette()
        self._icon_label.setPixmap(
            get_svg_icon("upload", color=pal.dropzone_border, size=24).pixmap(24, 24)
        )

    def apply_theme(self) -> None:
        # Tema değişiminde ikonu tazeler / Refreshes icon on theme change
        self._set_icon()

    def _build_info_container(self) -> QWidget:
        # Seçilen dosya bilgi kutusunu oluşturur / Builds selected file info container
        self._info_icon = QLabel()
        self._info_title = QLabel()
        self._info_title.setStyleSheet("font-weight: 700; font-size: 14px;")
        self._info_meta = QLabel()
        self._info_meta.setProperty("class", "muted")

        info_text_col = QVBoxLayout()
        info_text_col.addWidget(self._info_title)
        info_text_col.addWidget(self._info_meta)

        self._change_btn = QPushButton(UIStrings.BROWSE_BTN)
        self._change_btn.clicked.connect(self._browse)
        self._clear_btn = QPushButton(UIStrings.DROPZONE_CLEAR)
        self._clear_btn.clicked.connect(self.clear)

        info_row = QHBoxLayout()
        info_row.addWidget(self._info_icon)
        info_row.addLayout(info_text_col)
        info_row.addStretch()
        info_row.addWidget(self._change_btn)
        info_row.addWidget(self._clear_btn)

        container = QWidget()
        container.setLayout(info_row)
        container.hide()
        return container

    def retranslate_ui(self) -> None:
        # Arayüz diline göre metinleri günceller / Updates texts for active language
        self.setAccessibleName(UIStrings.DROPZONE_PROMPT)
        self._prompt_label.setText(UIStrings.DROPZONE_PROMPT)
        self._hint_label.setText(UIStrings.DROPZONE_HINT)
        self._browse_btn.setText(UIStrings.BROWSE_BTN)
        self._clear_btn.setText(UIStrings.DROPZONE_CLEAR)
        self._change_btn.setText(UIStrings.BROWSE_BTN)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Kutunun boş alanına tıklandığında da dosya seçiciyi açar / Opens dialog on box click
        if event.button() == Qt.MouseButton.LeftButton and not self._current_path:
            self._browse()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragHover", "true")
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragHover", "false")
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragHover", "false")
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.set_file_path(path)

    def _browse(self) -> None:
        filters = (
            "Tüm Desteklenen Belgeler (*.epub *.pdf *.docx *.png *.jpg *.jpeg *.webp *.bmp *.tiff *.lkproj);;"
            "Belgeler (*.epub *.pdf *.docx *.lkproj);;Görseller (*.png *.jpg *.jpeg *.webp *.bmp *.tiff)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Belge Seç", "", filters)
        if path:
            self.set_file_path(path)

    def set_file_path(self, path: str) -> None:
        # Seçilen dosya bilgisini gösterir ve sinyal yayar / Displays file info and emits signal
        self._current_path = path
        p = Path(path)
        if p.exists():
            size_str = _format_size(p.stat().st_size)
            ext_badge = p.suffix.upper().replace(".", "")
            self._info_title.setText(p.name)
            self._info_meta.setText(f"Tür: {ext_badge} | Boyut: {size_str} | Konum: {p.parent}")
            self._info_icon.setPixmap(
                get_svg_icon("document", color=ThemeManager.current_palette().accent, size=28).pixmap(28, 28)
            )
            self._info_icon.setFixedSize(28, 28)
            self._prompt_label.hide()
            self._hint_label.hide()
            self._browse_btn.hide()
            self._icon_label.hide()
            self._info_container.show()
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.file_selected.emit(path)

    def clear(self) -> None:
        # Seçili dosyayı temizler / Clears the selected file
        self._current_path = ""
        self._info_container.hide()
        self._icon_label.show()
        self._prompt_label.show()
        self._hint_label.show()
        self._browse_btn.show()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_selected.emit("")
