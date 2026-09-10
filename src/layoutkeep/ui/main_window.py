"""Top-level window: header, job setup, progress, completion.

Üst çubuk, kurulum ekranı, ilerleme ekranı ve tamamlandı ekranını birleştiren ana pencere.
Çeviri bitince gözden geçirme editörü açılmaz; kullanıcıya çıktıyı açma/klasörde gösterme/
yeni çeviri seçenekleri sunulur. Gözden geçirme editörü kaldırıldı (eski D6 akışı).
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from layoutkeep.ui.completion import CompletionWidget
from layoutkeep.ui.header import HeaderBar
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.progress import ProgressWidget
from layoutkeep.ui.settings import app_settings
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager
from layoutkeep.ui.worker import TranslationWorker


class MainWindow(QWidget):
    # Ana pencere bileşeni / Main application window widget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rootWindow")
        self.setWindowTitle("LayoutKeep")
        # Wide enough for the header's stepper and the four metric cards in a row, which is
        # what the mock-ups show. At 880 the stepper labels were clipped and the progress card
        # had to stack its figures two-by-two.
        # Fits a 1366x768 laptop with room to spare; the header sheds its subtitle and
        # shortens the step labels below this rather than forcing the window wider.
        self.resize(700, 660)
        # Small enough for a laptop screen, and not smaller than the screens can draw: a
        # minimum below what the layout needs does not shrink anything, it overlaps the rows.
        self.setMinimumSize(700, 540)
        self._settings = app_settings()

        self._init_subwidgets()
        self._setup_layout()
        self._wire_signals()
        self._restore_theme()
        self._restore_ui_language()

    def _init_subwidgets(self) -> None:
        # Alt bileşenleri oluşturur / Instantiates subwidgets
        self._header = HeaderBar(self)
        self._stack = QStackedWidget(self)
        self._setup = JobSetupWidget()
        self._progress = ProgressWidget()
        self._completion = CompletionWidget()

        self._stack.addWidget(self._setup)
        self._stack.addWidget(self._progress)
        self._stack.addWidget(self._completion)
        #: Set when a job starts, read when it finishes.
        self._last_output_path = ""
        self._completion.back_to_setup_requested.connect(self._return_to_setup)
        self._worker: TranslationWorker | None = None

    def _setup_layout(self) -> None:
        # Ana dikey düzeni kurar / Sets up main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._header.tweaks_requested.connect(self._open_tweaks)
        layout.addWidget(self._header)
        layout.addWidget(self._stack)

    def _wire_signals(self) -> None:
        # Olay ve sinyal bağlantılarını yapar / Wires events and signals
        self._header.theme_toggled.connect(self._on_theme_changed)
        self._header.ui_language_changed.connect(self._on_ui_language_changed)
        self._setup.job_ready.connect(self._start_job)
        self._progress.cancel_requested.connect(self._cancel_job)
        self._progress.pause_requested.connect(self._pause_job)
        self._progress.resume_requested.connect(self._resume_job)

    def _restore_theme(self) -> None:
        # Kayıtlı tema tercihini uygular / Applies saved theme preference
        is_dark = self._settings.value("dark_mode", False, type=bool)
        ThemeManager.set_dark(is_dark)
        self._apply_current_theme()

    def _restore_ui_language(self) -> None:
        # Kayıtlı arayüz dilini yükler ve uygular / Restores and applies saved UI language
        lang = str(self._settings.value("ui_language", "en"))
        UIStrings.set_language(lang)
        self._header.set_active_language(lang)
        self.retranslate_ui()

    def _on_ui_language_changed(self, lang: str) -> None:
        # Arayüz dili değiştiğinde ayarı kaydeder ve metinleri günceller / Handles UI language change
        self._settings.setValue("ui_language", lang)
        UIStrings.set_language(lang)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        # Tüm alt bileşenlerin metinlerini güncel dilde yeniler / Retranslates all subwidgets
        self._header.retranslate_ui()
        self._setup.retranslate_ui()
        self._progress.retranslate_ui()
        self._completion.retranslate_ui()

    def _on_theme_changed(self, is_dark: bool) -> None:
        # Tema değiştiğinde QSS'i yeniler ve kaydeder / Refreshes QSS and saves on theme change
        self._settings.setValue("dark_mode", is_dark)
        self._apply_current_theme()

    def _apply_current_theme(self) -> None:
        # Güncel stil sayfasını tüm uygulamaya uygular / Applies current stylesheet to app
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(ThemeManager.get_stylesheet())
        self._setup.apply_theme()
        self._completion.apply_theme()
        self._progress.apply_theme()
        self._header.set_active_step(self._stack.currentIndex() + 1)

    def _start_job(self, config: JobConfig) -> None:
        # Çeviri işini başlatır / Starts the translation job
        if not config.input_path or not config.output_path:
            QMessageBox.warning(self, "Eksik bilgi", "Girdi ve çıktı dosyası seçilmeli.")
            return

        self._last_output_path = config.output_path
        self._stack.setCurrentWidget(self._progress)
        self._header.set_active_step(2)
        self._progress.start()
        self._progress.set_model_name(config.provider.model)

        self._worker = TranslationWorker(config, self)
        self._worker.progress.connect(self._progress.set_progress)
        self._worker.progress_detailed.connect(self._progress.set_progress_detailed)
        self._worker.active_segment.connect(self._progress.set_active_segment)
        self._worker.segment_translated.connect(self._progress.append_segment_pair)
        self._worker.job_stats.connect(self._completion.set_stats)
        self._worker.review_flags.connect(self._progress.set_review_flags)
        self._worker.status.connect(self._progress.set_status)
        self._worker.memory_stats.connect(self._progress.set_memory_stats)
        self._worker.batch_timeout.connect(self._progress.set_batch_timeout)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def closeEvent(self, event) -> None:
        # Pencere kapanırken çalışan iş parçacığını güvenle durdurur / Safely stops worker on close
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1500)
        super().closeEvent(event)

    def _cancel_job(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _pause_job(self) -> None:
        # Çeviriyi duraklatır / Pauses the translation job
        if self._worker is not None:
            self._worker.pause()

    def _resume_job(self) -> None:
        # Çeviriye devam eder / Resumes the translation job
        if self._worker is not None:
            self._worker.resume()

    def _on_finished(self, project_path: str) -> None:
        # İş tamamlandığında tamamlandı ekranını gösterir / Shows completion screen
        self._progress.finish(f"tamamlandı: {project_path}")
        # Çıktıyı göster: dosya varsa aç/klasör butonları etkinleşir.
        self._completion.set_output_path(self._last_output_path)
        self._stack.setCurrentWidget(self._completion)
        self._header.set_active_step(3)

    def _open_tweaks(self) -> None:
        # Gelişmiş ayarlar penceresini açar / Opens the advanced settings dialog
        from layoutkeep.ui.tweaks_dialog import TweaksDialog

        TweaksDialog(self).exec()

    def _return_to_setup(self) -> None:
        # Tamamlandı ekranından ilk adıma döner / Returns to step 1 after completion
        self._stack.setCurrentWidget(self._setup)
        self._header.set_active_step(1)

    def _on_failed(self, message: str) -> None:
        # İş başarısız olduğunda bildirim verir / Shows error on failure and returns to setup
        self._progress.finish(f"hata: {message}")
        QMessageBox.critical(self, "Çeviri başarısız", message)
        self._stack.setCurrentWidget(self._setup)
        self._header.set_active_step(1)
