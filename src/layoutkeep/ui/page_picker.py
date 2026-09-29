"""Choosing the page range by looking at the pages.

Sayfa aralığını sayfalara bakarak seçmek: küçük resimler, tıkla-işaretle, aralık metni otomatik.

WHY THIS EXISTS: the range was a text field ("1-5, 8"), so choosing "the chapter with the tables"
meant opening the PDF elsewhere, finding the page numbers, and typing them back - and a PDF whose
printed page numbers differ from its physical ones (front matter in roman numerals) made the typed
number point at the wrong page. The picker shows every page as a thumbnail, ticked or not, and
writes the same range text the field already takes, so nothing downstream changes: the field stays
the single source of the range, and can still be typed into.

Thumbnails are rendered in small batches on the event loop, so a long book opens at once and fills
in; they are rendered once at the largest size and the size slider only scales them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core.range_helper import format_page_range, parse_page_range
from layoutkeep.ui.strings import UIStrings

#: Thumbnail width limits in pixels: rendered once at the largest, shown at the slider's value.
#: Küçük resim genişliği sınırları (piksel): en büyükte bir kez çizilir, kaydırıcı ölçekler.
THUMB_MIN, THUMB_MAX, THUMB_START = 60, 220, 120

#: Pages rendered per event-loop turn: small enough that the window stays responsive.
#: Olay döngüsünün her turunda çizilen sayfa sayısı.
RENDER_BATCH = 6


class PagePickerDialog(QDialog):
    """Every page of a PDF as a ticked thumbnail; `selected_pages()` is what the person kept."""

    def __init__(self, pdf_path: str | Path, selected: set[int] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        import pymupdf

        self.setWindowTitle(UIStrings.PICKER_TITLE)
        self.resize(760, 560)
        self._document = pymupdf.open(str(pdf_path))
        self._next_to_render = 0

        self._list = QListWidget()
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setSpacing(6)
        total = self._document.page_count
        for number in range(1, total + 1):
            item = QListWidgetItem(str(number))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            ticked = selected is None or number in selected
            item.setCheckState(Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.itemChanged.connect(self._update_count)

        self._size = QSlider(Qt.Orientation.Horizontal)
        self._size.setRange(THUMB_MIN, THUMB_MAX)
        self._size.setValue(THUMB_START)
        self._size.setToolTip(UIStrings.PICKER_SIZE)
        self._size.valueChanged.connect(self._resize_icons)
        self._resize_icons(THUMB_START)

        self._count = QLabel()
        self._count.setProperty("class", "muted")
        caption = QLabel(UIStrings.PICKER_CAPTION)
        caption.setWordWrap(True)
        caption.setProperty("class", "muted")
        select_all = QPushButton(UIStrings.PICKER_ALL)
        select_all.clicked.connect(lambda: self.set_all(True))
        select_none = QPushButton(UIStrings.PICKER_NONE)
        select_none.clicked.connect(lambda: self.set_all(False))
        row = QHBoxLayout()
        row.addWidget(select_all)
        row.addWidget(select_none)
        row.addWidget(self._count, 1)
        row.addWidget(QLabel(UIStrings.PICKER_SIZE))
        row.addWidget(self._size)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout = QVBoxLayout(self)
        layout.addWidget(caption)
        layout.addWidget(self._list, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

        self._update_count()
        # Pencereye ait zamanlayıcı: pencere silinince durur / Owned by the dialog, so it dies with it
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_batch)
        self._timer.start()

    # -- thumbnails / küçük resimler ------------------------------------------
    def _render_batch(self) -> None:
        if self._document.is_closed:  # the dialog closed while batches were queued
            self._timer.stop()
            return
        stop = min(self._next_to_render + RENDER_BATCH, self._document.page_count)
        for index in range(self._next_to_render, stop):
            self._list.item(index).setIcon(QIcon(self._thumbnail(index)))
        self._next_to_render = stop
        if stop >= self._document.page_count:
            self._timer.stop()

    def _thumbnail(self, index: int) -> QPixmap:
        import pymupdf

        page = self._document[index]
        zoom = THUMB_MAX / max(page.rect.width, 1.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image.copy())

    def render_all(self) -> None:
        """Render every remaining thumbnail now (what the event loop does in batches)."""
        while self._next_to_render < self._document.page_count:
            self._render_batch()

    def _resize_icons(self, width: int) -> None:
        # Kaydırıcı yalnız ölçekler; sayfa yeniden çizilmez / The slider only scales
        self._list.setIconSize(QSize(width, int(width * 1.42)))

    # -- selection / seçim ----------------------------------------------------
    def set_all(self, ticked: bool) -> None:
        state = Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
        for index in range(self._list.count()):
            self._list.item(index).setCheckState(state)

    def set_page(self, number: int, ticked: bool) -> None:
        """Tick or untick one page (1-based), as a click on its box does."""
        state = Qt.CheckState.Checked if ticked else Qt.CheckState.Unchecked
        self._list.item(number - 1).setCheckState(state)

    def selected_pages(self) -> set[int]:
        return {
            index + 1
            for index in range(self._list.count())
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        }

    def range_text(self) -> str:
        """The selection as the range field's text; empty when every page is ticked."""
        pages = self.selected_pages()
        return "" if len(pages) == self._list.count() else format_page_range(pages)

    def _update_count(self, *_args) -> None:
        # Hiç sayfa seçilmemişse onay kapalı: boş aralık "tümü" demektir
        # Nothing ticked disables OK: an empty range would mean the whole document
        chosen = len(self.selected_pages())
        self._count.setText(UIStrings.PICKER_COUNT.format(n=chosen, total=self._list.count()))
        self._ok.setEnabled(chosen > 0)

    def done(self, result: int) -> None:
        self._timer.stop()
        self._document.close()
        super().done(result)


def pick_pages(parent: QWidget, input_path: str, current: str) -> str | None:
    """Open the picker on `input_path` with `current` ticked; the new range text, or None.

    PDF only: the other formats have no fixed pages to show (an EPUB's "pages" are its chapters).
    Yalnız PDF; iptal ya da uygun olmayan dosyada None döner.
    """
    path = Path(input_path) if input_path else None
    if path is None or path.suffix.lower() != ".pdf" or not path.exists():
        QMessageBox.information(parent, UIStrings.PICKER_TITLE, UIStrings.RANGE_PICK_PDF_ONLY)
        return None
    import pymupdf

    with pymupdf.open(str(path)) as document:
        total = document.page_count
    selected = parse_page_range(current, total) if current.strip() else None
    dialog = PagePickerDialog(path, selected, parent)
    if not dialog.exec():
        return None
    return dialog.range_text()
