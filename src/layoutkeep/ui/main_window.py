"""Top-level window: header, job setup, progress, completion.

Üst çubuk, kurulum ekranı, ilerleme ekranı ve tamamlandı ekranını birleştiren ana pencere.
Çeviri bitince gözden geçirme editörü açılmaz; kullanıcıya çıktıyı açma/klasörde gösterme/
yeni çeviri seçenekleri sunulur. Gözden geçirme editörü kaldırıldı (eski D6 akışı).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from layoutkeep import __version__
from layoutkeep.ui.completion import CompletionWidget
from layoutkeep.ui.floating_bridge import FloatingBarBridge
from layoutkeep.ui.floating_progress import FloatingProgress
from layoutkeep.ui.header import HeaderBar
from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.progress import ProgressWidget
from layoutkeep.ui.run_controller import RunController
from layoutkeep.ui.settings import app_settings
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.welcome import WelcomeDialog
from layoutkeep.ui.window_appearance import WindowAppearance
from layoutkeep.ui.worker import TranslationWorker


def _welcome_is_wanted() -> bool:
    """Whether a first run may open the introduction.

    Not in an automated session. A modal dialog with nobody to click it is an infinite hang, and
    both the test suite and any scripted launch land there: the application opens off screen, the
    timer fires, and the process waits forever. `LAYOUTKEEP_NO_WELCOME=1` says so explicitly for
    anything the off-screen check does not cover.
    """
    if os.environ.get("LAYOUTKEEP_NO_WELCOME"):
        return False
    return QApplication.platformName() != "offscreen"


class MainWindow(QWidget):
    # Ana pencere bileşeni / Main application window widget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rootWindow")
        self.setWindowTitle(UIStrings.APP_TITLE)
        # The size is fixed once the layout is built, at the smallest size that layout actually
        # needs - see the end of __init__. It used to open at 700x660 with a 700x540 minimum and
        # stay resizable; the reader wanted a compact window, and a resizable one only ever gets
        # resized by accident.
        self._settings = app_settings()

        self._init_subwidgets()
        self._setup_layout()
        self._wire_signals()
        self._appearance.restore_theme()
        self._appearance.restore_language()
        # The smallest size the built layout asks for, fixed: the reader wanted a compact window
        # and no reason to resize it. `minimumSizeHint` is what the pages actually need, so nothing
        # is clipped; the floor guards against a system where the hint comes out implausibly small.
        hint = self.minimumSizeHint()
        self.setFixedSize(max(620, hint.width()), max(500, hint.height()))
        # After the window is on screen, so the introduction is not the first thing Qt paints.
        QTimer.singleShot(0, self._maybe_show_welcome)

    def _init_subwidgets(self) -> None:
        # Alt bileşenleri oluşturur / Instantiates subwidgets
        self._header = HeaderBar(self)
        self._stack = QStackedWidget(self)
        self._setup = JobSetupWidget()
        self._progress = ProgressWidget()
        self._completion = CompletionWidget()
        #: Owned by this window (kept alive by this reference, destroyed with it in `closeEvent`),
        #: but a *parentless* top-level window on purpose. A Qt window with a parent is an owned
        #: window on Windows, and Windows minimises an owned window together with its owner - so
        #: minimising the main window took the bar down with it, which is the one thing the bar
        #: exists to avoid. Parentless was tried before and crashed the UI suite because the
        #: widget outlived the window that created it; the fix is not a parent but an explicit
        #: `deleteLater()` in `closeEvent`, and never touching it afterwards.
        self._floating: FloatingProgress | None = FloatingProgress(None)

        self._stack.addWidget(self._setup)
        self._stack.addWidget(self._progress)
        self._stack.addWidget(self._completion)
        #: Set when a job starts, read when it finishes.
        self._last_output_path = ""
        self._completion.back_to_setup_requested.connect(self._return_to_setup)
        # Koşunun sahibi: worker, sinyal bağlantıları, duraklat/iptal / The run's owner
        self._run = RunController(
            self,
            header=self._header,
            stack=self._stack,
            progress=self._progress,
            completion=self._completion,
            bar=lambda: self._bar,
            output_path=lambda: self._last_output_path,
            set_output_path=self._set_last_output_path,
            sync_bar=self._sync_bar_visibility,
            to_setup=self._return_to_setup,
        )
        # Tema ve arayüz dili bu pencerenin kabuğunda tutulur / Theme and language live here
        self._appearance = WindowAppearance(
            self._settings,
            self._header,
            screens=lambda: (self._setup, self._completion, self._progress, self._bar),
            step=lambda: self._stack.currentIndex() + 1,
        )
        # Pencere ile yüzen çubuk arasındaki geçişler / Every route between window and bar
        self._bar_bridge = FloatingBarBridge(
            self,
            bar=lambda: self._floating,
            on_new_job=self._return_to_setup,
            on_pause=self._run.pause,
            on_resume=self._run.resume,
            output_path=lambda: self._last_output_path,
        )

    def _set_last_output_path(self, path: str) -> None:
        # Bir koşu başlarken çıktı yolunu pencereye yazar / The run records its output path here
        self._last_output_path = path

    @property
    def _worker(self) -> TranslationWorker | None:
        """The run's worker. The controller owns it; the tests set this attribute directly."""
        return self._run.worker

    @_worker.setter
    def _worker(self, worker: TranslationWorker | None) -> None:
        self._run.worker = worker

    @property
    def _bar(self) -> FloatingProgress:
        """The floating bar. It exists for the whole life of the window; `closeEvent` clears it."""
        bar = self._floating
        if bar is None:  # only reachable after `closeEvent` has taken it down
            raise RuntimeError("the floating bar was already destroyed")
        return bar

    def _switch_to_bar(self) -> None:
        """Hand the run to the floating bar; see `FloatingBarBridge.switch_to_bar`."""
        self._bar_bridge.switch_to_bar(self._worker)

    def _sync_bar_visibility(self) -> None:
        """Only one of the window and the bar is on screen; see `FloatingBarBridge.sync`."""
        self._bar_bridge.sync()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_bar_visibility()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync_bar_visibility()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_bar_visibility()

    def _on_ui_language_changed(self, lang: str) -> None:
        # Arayüz dili değiştiğinde ayarı kaydeder ve metinleri günceller / Handles UI language change
        # İnce delege: testler bu adı çağırıyor / Thin delegate, the tests call this name
        self._appearance.store_language(lang)

    def _setup_layout(self) -> None:
        # Ana dikey düzeni kurar / Sets up main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._header.tweaks_requested.connect(self._open_tweaks)
        self._header.help_requested.connect(self.show_help)
        self._header.bar_requested.connect(self._switch_to_bar)
        layout.addWidget(self._header)
        layout.addWidget(self._stack)

    def _wire_signals(self) -> None:
        # Olay ve sinyal bağlantılarını yapar / Wires events and signals
        self._header.theme_toggled.connect(self._appearance.store_theme)
        self._header.ui_language_changed.connect(self._appearance.store_language)
        self._setup.job_ready.connect(self._run.start)
        self._progress.cancel_requested.connect(self._run.cancel)
        self._progress.pause_requested.connect(self._run.pause)
        self._progress.resume_requested.connect(self._run.resume)
        self._bar.restore_requested.connect(self._bar_bridge.restore_window)
        self._bar.new_job_requested.connect(self._bar_bridge.start_new_job)
        self._bar.open_output_requested.connect(self._bar_bridge.open_output)
        self._bar.pause_toggled.connect(self._bar_bridge.toggle_pause)

    def closeEvent(self, event) -> None:
        # Pencere kapanırken çalışan iş parçacığını güvenle durdurur / Safely stops worker on close
        self._run.stop()
        # The bar is a parentless top-level window, so closing the application has to take it down
        # explicitly - and delete it, not merely hide it: an orphaned top-level widget outliving
        # this window is what crashed the UI suite the first time this was tried.
        if self._floating is not None:
            self._floating.close()
            self._floating.deleteLater()
            self._floating = None
        super().closeEvent(event)

    def _on_finished(self, project_path: str) -> None:
        # İş tamamlandığında tamamlandı ekranını gösterir / Shows completion screen
        # İnce delege: testler bu adı çağırıyor / Thin delegate, the tests call this name
        self._run.finish(project_path)

    def show_help(self) -> None:
        """Open the help screen; the header's "?" and the welcome screen both land here."""
        from layoutkeep.ui.help_dialog import show_help

        show_help(self)

    def _maybe_show_welcome(self) -> None:
        """The introduction on a first run - and again after an update.

        The version matters: with a bare boolean, installing a new build left the flag set and the
        user saw nothing at all, which reads as "the update did not happen". Storing the version
        the screen was shown for makes an update greet the reader once, the way a release should.
        """
        if not _welcome_is_wanted():
            return
        shown = bool(self._settings.value("welcome_shown", False, type=bool))
        seen_version = str(self._settings.value("welcome_shown_version", ""))
        if shown and seen_version == __version__:
            return
        self.show_welcome()

    def show_welcome(self) -> None:
        """Open the introduction and let its language and theme choices reach the application."""
        dialog = WelcomeDialog(self)
        dialog.language_changed.connect(self._appearance.store_language)
        dialog.theme_changed.connect(self._appearance.store_theme)
        dialog.exec()

    def _open_tweaks(self) -> None:
        # Gelişmiş ayarlar penceresini açar / Opens the advanced settings dialog
        from layoutkeep.ui.tweaks_dialog import TweaksDialog

        dialog = TweaksDialog(self, document_path=self._setup.input_path())
        dialog.welcome_requested.connect(self.show_welcome)
        dialog.exec()

    def _return_to_setup(self) -> None:
        # Tamamlandı ekranından ilk adıma döner / Returns to step 1 after completion
        self._stack.setCurrentWidget(self._setup)
        self._header.set_active_step(1)
