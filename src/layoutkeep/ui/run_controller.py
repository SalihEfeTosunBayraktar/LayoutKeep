"""Bir çeviri koşusu ve beslendiği ekranlar / One translation run and the screens it feeds.

İş parçacığını kurar, sinyallerini ilerleme kartına, tamamlanma ekranına ve yüzen çubuğa bağlar;
başlatma, duraklatma, iptal, tamamlanma ve hata akışını yürütür. Kart ile çubuk aynı sinyalleri
okuduğu için ikisi bir koşu hakkında çelişemez - o söz tek yerde durur.

Kendi Qt durumunu tutmaz: widget'lar ve geri çağırmalar parametre olarak gelir, worker ise bu
nesnede durur (pencere `_worker` adını ona delege eder).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QStackedWidget, QWidget

from layoutkeep.core import tunables
from layoutkeep.ui.completion import CompletionWidget
from layoutkeep.ui.floating_progress import FloatingProgress
from layoutkeep.ui.header import HeaderBar
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.progress import ProgressWidget
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.worker import TranslationWorker


class RunController:
    """Starts, pauses, cancels and finishes one translation run."""

    def __init__(
        self,
        window: QWidget,
        *,
        header: HeaderBar,
        stack: QStackedWidget,
        progress: ProgressWidget,
        completion: CompletionWidget,
        bar: Callable[[], FloatingProgress],
        output_path: Callable[[], str],
        set_output_path: Callable[[str], None],
        sync_bar: Callable[[], None],
        to_setup: Callable[[], None],
    ) -> None:
        self._window = window
        self._header = header
        self._stack = stack
        self._progress = progress
        self._completion = completion
        self._bar = bar
        self._output_path = output_path
        self._set_output_path = set_output_path
        self._sync_bar = sync_bar
        self._to_setup = to_setup
        self.worker: TranslationWorker | None = None

    # ------------------------------------------------------------------- koşu
    def start(self, config: JobConfig) -> None:
        # Çeviri işini başlatır / Starts the translation job
        if not config.input_path or not config.output_path:
            QMessageBox.warning(self._window, UIStrings.MISSING_FILES_DIALOG_TITLE, UIStrings.MISSING_FILES_DIALOG_BODY)
            return

        self._set_output_path(config.output_path)
        self._stack.setCurrentWidget(self._progress)
        self._header.set_active_step(2)
        self._progress.start()
        self._progress.set_model_name(config.provider.model)

        worker = TranslationWorker(config, self._window)
        self.worker = worker
        self._connect(worker)
        if bool(tunables.get("ui.floating_progress")):
            self._bar().start_job(Path(config.input_path).name)
            self._sync_bar()
        worker.start()

    def _connect(self, worker: TranslationWorker) -> None:
        # İş parçacığının sinyallerini ekranlara bağlar / Wires the worker's signals to the screens
        worker.progress.connect(self._progress.set_progress)
        worker.progress_detailed.connect(self._progress.set_progress_detailed)
        worker.active_segment.connect(self._progress.set_active_segment)
        worker.segment_translated.connect(self._progress.append_segment_pair)
        worker.job_stats.connect(self._completion.set_stats)
        worker.review_flags.connect(self._progress.set_review_flags)
        worker.status.connect(self._progress.set_status)
        worker.memory_stats.connect(self._progress.set_memory_stats)
        worker.batch_timeout.connect(self._progress.set_batch_timeout)
        worker.finished_ok.connect(self.finish)
        worker.failed.connect(self.fail)
        # The summary bar reads the same signals as the card, so the two cannot disagree.
        worker.progress.connect(self._bar().set_progress)
        worker.status.connect(self._bar().set_phase)
        worker.finished_ok.connect(self._bar().finish)
        worker.failed.connect(self._bar().fail)

    # ---------------------------------------------------------------- kumanda
    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def pause(self) -> None:
        # Çeviriyi duraklatır / Pauses the translation job
        if self.worker is not None:
            self.worker.pause()

    def resume(self) -> None:
        # Çeviriye devam eder / Resumes the translation job
        if self.worker is not None:
            self.worker.resume()

    def stop(self) -> None:
        """Stop a running worker before the window that owns it goes away."""
        worker = self.worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(1500)

    # ------------------------------------------------------------------ sonuç
    def finish(self, project_path: str) -> None:
        # İş tamamlandığında tamamlandı ekranını gösterir / Shows completion screen
        self._progress.finish(UIStrings.COMPLETED_WITH_FILE.format(project_path))
        # Çıktıyı göster: dosya varsa aç/klasör butonları etkinleşir.
        self._completion.set_output_path(self._output_path())
        self._stack.setCurrentWidget(self._completion)
        self._header.set_active_step(3)

    def fail(self, message: str) -> None:
        # İş başarısız olduğunda bildirim verir / Shows error on failure and returns to setup
        self._progress.finish(f"hata: {message}")
        QMessageBox.critical(self._window, UIStrings.TRANSLATION_FAILED_DIALOG_TITLE, message)
        self._to_setup()
