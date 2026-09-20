"""A small always-on-top window that follows a translation job.

WHY THIS EXISTS: translating a book takes tens of minutes, and the main window is a
full-size one, so following a run means either leaving a big window in the way or not
being able to see it at all. The user asked for something that stays out of the way
while still answering, at a glance - which document is being worked on, which phase it
is in, how far along it is, and how to get back to the application for the details. On
success it turns into the way to open the output or start the next job, and it folds
down to a pill when even that is in the way.

It listens to exactly the same worker signals the in-window progress card does, so the
two can never disagree about a run; the card stays the place with the detail (live
segment previews, per-phase timings), this bar is the place with the summary.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFontMetrics, QMouseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.progress import format_phase
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

_MIN_WIDTH = 480  # wide enough for a book title and its counters, small enough to forget
_PILL_WIDTH = 132  # folded: the percentage and the button that brings the rest back
_TITLE_ROOM = 300  # pixels the title may use before it is elided
_TOP_MARGIN = 24  # keeps the bar clear of a maximised window's own title bar
_MAX_WIDTH = 16777215  # Qt's own maximum widget width, named for the unfolded state
_KEEP_VISIBLE = 80  # pixels of the bar that must stay on screen so it can be dragged back


class WindowDrag(QObject):
    """Move a frameless window by dragging one of its widgets.

    WHY THIS EXISTS: a frameless card has no title bar, and Qt delivers the press to the child
    widget under the cursor - a label - not to the window, so drag handlers written on the window
    itself never run. This installs one event filter on the widgets that are safe to grab (never
    the buttons) and moves the window by the distance the pointer travelled.
    """

    def __init__(self, window: QWidget, handles: Sequence[QWidget]) -> None:
        #: Qt owns the relationship; Python holds no strong reference to the window on purpose.
        #: Keeping one created a parent/child reference cycle that outlived the widget: the next
        #: global stylesheet application then walked a widget whose C++ object was already gone
        #: and took the process down with a heap-corruption crash.
        super().__init__(window)
        self._offset: QPoint | None = None
        for handle in handles:
            handle.installEventFilter(self)

    def dragging(self) -> bool:
        return self._offset is not None

    def _target(self) -> QWidget | None:
        """The window to move, asked of Qt rather than remembered."""
        parent = self.parent()
        return parent if isinstance(parent, QWidget) else None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            target = self._target()
            if target is not None and event.button() == Qt.MouseButton.LeftButton:
                self._offset = event.globalPosition().toPoint() - target.frameGeometry().topLeft()
            return False  # the click still belongs to the widget, which may act on it
        if kind == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
            if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                target = self._target()
                if target is not None:
                    target.move(self._kept_on_screen(event.globalPosition().toPoint() - self._offset, target))
                    return True
            return False
        if kind == QEvent.Type.MouseButtonRelease:
            self._offset = None
        return False

    def _kept_on_screen(self, wanted: QPoint, target: QWidget) -> QPoint:
        """Never let a drag park the bar somewhere the user cannot reach it again.

        A window dragged past a screen edge - or left behind after a monitor is unplugged - has no
        title bar to grab and no way back, so the position is clamped to leave a strip visible.
        """
        screen = QApplication.screenAt(target.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return wanted
        area = screen.availableGeometry()
        return QPoint(
            min(max(wanted.x(), area.left() - target.width() + _KEEP_VISIBLE), area.right() - _KEEP_VISIBLE),
            min(max(wanted.y(), area.top()), area.bottom() - _KEEP_VISIBLE),
        )


class FloatingProgress(QFrame):
    """Frameless card: one line of state, a bar, and the ways out of it."""

    restore_requested = Signal()  # the user wants the full window back
    new_job_requested = Signal()  # start the next document
    open_output_requested = Signal()  # open the translated file
    pause_toggled = Signal()  # pause when running, resume when paused

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "running"  # running | done | failed
        self._paused = False
        self._folded = False  # folded down to the pill
        self._placed = False  # the user may have dragged it; only place it once
        self._output_path = ""
        self._document = ""
        self._phase = ""
        self._counts = (0, 0)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(_MIN_WIDTH)
        self._build()
        # The card, its labels and the percentage move the window; the buttons never do.
        self._drag = WindowDrag(self, [self._card, self._title, self._detail, self._percent])
        self.apply_theme()
        self._refresh()

    # ---------------------------------------------------------------- construction

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._card = QFrame()
        self._card.setObjectName("floatCard")
        outer.addWidget(self._card)

        rows = QVBoxLayout(self._card)
        self._rows = rows
        rows.setContentsMargins(14, 10, 14, 10)
        rows.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._title = QLabel()
        self._title.setObjectName("floatTitle")
        self._percent = QLabel("0%")
        self._percent.setObjectName("floatPercent")
        self._percent.setCursor(Qt.CursorShape.OpenHandCursor)
        top.addWidget(self._title, 1)
        top.addWidget(self._percent, 0, Qt.AlignmentFlag.AlignRight)
        rows.addLayout(top)

        self._detail = QLabel()
        self._detail.setObjectName("floatDetail")
        rows.addWidget(self._detail)

        self._bar = QProgressBar()
        self._bar.setObjectName("floatBar")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        rows.addWidget(self._bar)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._pause_button = QPushButton()
        self._pause_button.setObjectName("floatGhost")
        self._pause_button.clicked.connect(self._on_pause)
        self._restore_button = QPushButton()
        self._restore_button.setObjectName("floatPrimary")
        self._restore_button.clicked.connect(self.restore_requested.emit)
        self._output_button = QPushButton()
        self._output_button.setObjectName("floatSuccess")
        self._output_button.clicked.connect(self.open_output_requested.emit)
        self._new_button = QPushButton()
        self._new_button.setObjectName("floatGhost")
        self._new_button.clicked.connect(self.new_job_requested.emit)
        self._fold_button = QPushButton()
        self._fold_button.setObjectName("floatGhost")
        self._fold_button.clicked.connect(self.toggle_folded)
        buttons.addWidget(self._pause_button)
        buttons.addStretch(1)
        buttons.addWidget(self._output_button)
        buttons.addWidget(self._new_button)
        buttons.addWidget(self._restore_button)
        buttons.addWidget(self._fold_button)
        rows.addLayout(buttons)

    # ---------------------------------------------------------------------- theme

    def apply_theme(self) -> None:
        # Tema değişiminde renkleri token'lardan tazeler / Refreshes every colour from tokens
        palette = ThemeManager.current_palette()
        border = palette.success if self._state == "done" else (
            palette.error if self._state == "failed" else palette.border
        )
        self._card.setStyleSheet(
            f"#floatCard {{ background:{palette.surface}; border:1px solid {border};"
            f" border-radius:12px; }}"
            f"#floatTitle {{ color:{palette.text_primary}; font-weight:600; }}"
            f"#floatDetail {{ color:{palette.text_muted}; }}"
            f"#floatPercent {{ color:{palette.accent}; font-weight:600;"
            f" }}"
            f"QProgressBar#floatBar {{ background:{palette.surface_active};"
            f" border:none; border-radius:4px; }}"
            f"QProgressBar#floatBar::chunk {{ background:{self._chunk_color()};"
            f" border-radius:4px; }}"
            f"QPushButton#floatPrimary {{ background:{palette.accent}; color:{palette.accent_text};"
            f" border:none; border-radius:6px; padding:4px 12px; }}"
            f"QPushButton#floatSuccess {{ background:{palette.success}; color:{palette.accent_text};"
            f" border:none; border-radius:6px; padding:4px 12px; font-weight:600; }}"
            f"QPushButton#floatGhost {{ background:transparent; color:{palette.text_secondary};"
            f" border:1px solid {palette.border}; border-radius:6px; padding:4px 10px; }}"
        )

    def _chunk_color(self) -> str:
        palette = ThemeManager.current_palette()
        if self._state == "done":
            return palette.success
        if self._state == "failed":
            return palette.error
        return palette.accent

    # ----------------------------------------------------------------- public API

    def start_job(self, document: str, total: int = 0) -> None:
        """Show the bar for a new document, replacing whatever the last run left behind."""
        self._state = "running"
        self._paused = False
        self._output_path = ""
        self._document = document
        self._bar.setRange(0, max(1, total))
        self._bar.setValue(0)
        self._counts = (0, total)
        self._phase = ""
        self.apply_theme()
        self._refresh()
        self.show()
        self.raise_()

    def set_progress(self, done: int, total: int) -> None:
        self._bar.setRange(0, max(1, total))
        self._bar.setValue(min(done, total))
        self._counts = (done, total)
        self._refresh()

    def set_phase(self, status: str) -> None:
        # Faz metni geldiğinde gösterir / Shows the phase the worker announced
        self._phase = format_phase(status)
        self._refresh()

    def finish(self, output_path: str) -> None:
        self._state = "done"
        self._output_path = output_path
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        self._folded = False  # the end of a run is worth the space, even if it was folded away
        self.apply_theme()
        self._refresh()

    def fail(self, message: str) -> None:
        self._state = "failed"
        self._phase = message.splitlines()[0][:120] if message else UIStrings.FLOAT_FAILED
        self._folded = False
        self.apply_theme()
        self._refresh()

    def toggle_folded(self) -> None:
        """Fold the bar down to the percentage pill, or unfold it again."""
        self._folded = not self._folded
        self._refresh()

    def is_folded(self) -> bool:
        return self._folded

    def is_paused(self) -> bool:
        return self._paused

    def output_path(self) -> str:
        return self._output_path

    def retranslate_ui(self) -> None:
        # Dil değişiminde etiketleri yeniler / Refreshes labels after a language change
        self._refresh()

    # --------------------------------------------------------------------- display

    def _refresh(self) -> None:
        metrics = QFontMetrics(self._title.font())
        # The title is elided to fit the bar, so the full name is kept in the tooltip: an elided
        # name a reader cannot recover is a name they cannot check against the file they chose.
        self._title.setText(metrics.elidedText(self._document, Qt.TextElideMode.ElideMiddle, _TITLE_ROOM))
        self._title.setToolTip(self._document)
        done, total = self._counts
        percent = 100 if self._state == "done" else round(done / total * 100) if total else 0
        self._percent.setText(f"{percent}%")
        phase = self._phase or UIStrings.FLOAT_WAITING
        if self._state == "done":
            self._detail.setText(f"{UIStrings.FLOAT_DONE} · {phase}")
        elif self._state == "failed":
            self._detail.setText(f"{UIStrings.FLOAT_FAILED}: {phase}")
        else:
            self._detail.setText(f"{phase} · {UIStrings.FLOAT_SEGMENTS.format(done=done, total=total)}")
        self._pause_button.setText(UIStrings.FLOAT_RESUME if self._paused else UIStrings.FLOAT_PAUSE)
        self._restore_button.setText(UIStrings.FLOAT_RESTORE)
        self._output_button.setText(UIStrings.OPEN_OUTPUT_BTN)
        self._new_button.setText(UIStrings.BACK_TO_SETUP_BTN)
        self._fold_button.setText("▸" if self._folded else "—")
        self._fold_button.setToolTip(UIStrings.FLOAT_EXPAND if self._folded else UIStrings.FLOAT_FOLD)
        self._apply_visibility()
        self.adjustSize()

    def _apply_visibility(self) -> None:
        """One place decides what is on screen, so the folded state cannot contradict the run."""
        running = self._state == "running"
        expanded = not self._folded
        self._title.setVisible(expanded)
        self._detail.setVisible(expanded)
        self._bar.setVisible(expanded)
        self._pause_button.setVisible(expanded and running)
        self._output_button.setVisible(expanded and self._state == "done")
        self._new_button.setVisible(expanded and self._state == "done")
        self._restore_button.setVisible(expanded)
        if self._folded:
            self._rows.setContentsMargins(10, 6, 10, 6)
            self.setMinimumWidth(_PILL_WIDTH)
            self.setMaximumWidth(_PILL_WIDTH)
        else:
            self._rows.setContentsMargins(14, 10, 14, 10)
            self.setMinimumWidth(_MIN_WIDTH)
            self.setMaximumWidth(_MAX_WIDTH)

    def _on_pause(self) -> None:
        self._paused = not self._paused
        self._refresh()
        self.pause_toggled.emit()

    # ------------------------------------------------------------------ placement

    def showEvent(self, event: QShowEvent) -> None:
        # İlk gösterimde ekranın üst-ortasına yerleşir / Places itself top-centre on first show
        super().showEvent(event)
        if self._placed:
            return  # after a drag, the position the user chose is the position it keeps
        self._placed = True
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.adjustSize()
            self.move(area.center().x() - self.width() // 2, area.top() + _TOP_MARGIN)
