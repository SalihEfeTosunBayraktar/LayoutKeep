"""Background translation worker.

Runs entirely on a QThread so the main thread never blocks. It only calls into
`layoutkeep.core` and `layoutkeep.providers` - the same functions `cli.py` calls - and never
reimplements translation, fitting or I/O logic (see docs/CONTRACT.md, D1/D2).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    Document,
    Segment,
)
from layoutkeep.core.timing import PhaseTimer, TimingReport
from layoutkeep.ui import provider_factory
from layoutkeep.ui.document_finalizer import DocumentFinalizer
from layoutkeep.ui.document_io import load_layout_detector, read_document
from layoutkeep.ui.document_prep import DocumentPreparer
from layoutkeep.ui.fit_pass_runner import FitPassRunner
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.translation_loop import _run_translation_loop


class TranslationWorker(QThread):
    """Runs one translation job on a background thread.

    Signals carry every piece of state the UI needs; nothing is read back from the worker
    object itself after `start()`, so there is no cross-thread field access to race on.
    """

    progress = Signal(int, int)                 # segments done, segments total
    progress_detailed = Signal(int, int, int, int, float, str)  # done_seg, tot_seg, done_ch, tot_ch, speed, eta
    active_segment = Signal(int, str)           # active segment index (1-based), preview text
    #: One finished segment, for the live side-by-side view: (source, translation).
    segment_translated = Signal(str, str)
    #: End-of-job figures for the completion screen. Emitted before finished_ok.
    job_stats = Signal(dict)
    #: Segments flagged for review so far, and how many are done. Lets a job that is going
    #: badly be abandoned early instead of being watched to the end.
    review_flags = Signal(int, int)
    status = Signal(str)                        # short human-readable phase description
    memory_stats = Signal(int, int)             # hits, total lookups
    batch_timeout = Signal(float)               # seconds the current in-flight request is allowed
    finished_ok = Signal(str)                   # project path written on success
    failed = Signal(str)                        # error message

    def __init__(self, config: JobConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._cancelled = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        #: Wall clock at the start of _run, for the completion screen's total time.
        self._started_at: float | None = None
        #: Flags whose cause is the box rather than the text (core.review.BOX_CRUSHED), counted
        #: for the completion screen - a user reading "N need review" deserves to know how many
        #: of them are a layout problem no amount of rephrasing would fix.
        self._box_crushed = 0

    def pause(self) -> None:
        """Ask the loop to stop at the next chunk boundary.

        A request already in flight is not interrupted - with a slow local model that can be
        minutes - so the status says "pausing" rather than "paused". Claiming it had stopped
        while text kept arriving was the confusing part, not the wait.
        """
        self._pause_event.clear()
        self.status.emit(UIStrings.STATUS_PAUSING)

    def resume(self) -> None:
        # Çeviriye kaldığı yerden devam eder / Resumes translation from where it paused
        self._pause_event.set()
        self.status.emit(UIStrings.STATUS_RESUMING)

    def cancel(self) -> None:
        # Çeviriyi iptal eder / Cancels job safely
        self._cancelled = True
        self._pause_event.set()

    def _cleanup_resources(self) -> None:
        # Güvenli kaynak temizliği / Safe resource cleanup
        pass

    def run(self) -> None:
        try:
            self._run()
        except BaseException as exc:  # noqa: BLE001
            import traceback

            tb = traceback.format_exc()
            # Crash raporu cwd'ye değil, uygulamanın AppData konumuna yazılır (app.py'deki
            # _crash_log_path ile aynı yer). Böylece paketlenmiş uygulama Program Files'tan
            # başlatılsa bile yazma başarısız olmaz ve köke çöp log düşmez.
            from layoutkeep.ui.crashlog import crash_log_path

            try:
                log_dir = crash_log_path().parent
                log_dir.mkdir(parents=True, exist_ok=True)
                with crash_log_path().open("a", encoding="utf-8") as f:
                    f.write(f"\n[Worker Thread Error]\n{tb}\n")
            except OSError:
                pass
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _run(self) -> None:
        self._started_at = time.monotonic()
        config = self._config
        src = Path(config.input_path)
        out = Path(config.output_path)
        # Where the time went. Filled as the run goes and, when the user asked for it, written next
        # to the output at the end - the same directory, so the report travels with its document.
        self._timing = TimingReport(document=src.name)
        phases = PhaseTimer(self._timing)

        self.status.emit("reading document")
        # Read once, here: the detector is both what the reader uses and part of what the run
        # records about itself (`document_prep.DocumentPreparer._record_provenance`).
        detector = load_layout_detector()
        try:
            with phases.phase("read", src.suffix.lower() or "input"):
                doc = read_document(src, detector)
        except FileNotFoundError as exc:
            # A1: eksik/okunamayan girdi traceback degil, tek cumle / missing input → one line
            self.failed.emit(str(exc))
            return
        except ValueError as exc:
            self.failed.emit(str(exc))
            return
        doc.source_lang = config.source_lang
        doc.target_lang = config.target_lang

        # Hazırlığın tamamı (kaynakça, sözlük, konu haritası, aralık, bütçe) DocumentPreparer'da
        # yaşar; worker yalnız hangi sinyalin yayılacağına karar verir. / The whole preparation
        # lives in DocumentPreparer; the worker keeps the signals.
        prepared = DocumentPreparer(
            on_status=self.status.emit, build_provider=provider_factory.build_provider
        ).prepare(doc, src, out, config, phases=phases, layout_model=detector is not None)
        if prepared is None:
            self.failed.emit(UIStrings.get("ERROR_NO_TEXT"))
            return
        self._config = prepared.config  # parallel chains need the merged glossary (see commit 438e14c)

        self.progress.emit(0, prepared.total)
        self.progress_detailed.emit(0, prepared.total, 0, prepared.total_chars, 0.0, "")

        with phases.phase(
            "translate", f"{prepared.total} segments, {prepared.total_chars:,} chars"
        ):
            translated = _run_translation_loop(
                self,
                prepared.provider,
                prepared.memory,
                prepared.segments,
                prepared.total,
                prepared.total_chars,
                source_lang=prepared.config.source_lang,
                target_lang=prepared.config.target_lang,
                glossary=prepared.glossary,
            )
        if translated is None:
            return

        self._finalize_document(
            doc, translated, src, out, prepared.config, prepared.provider, phases
        )
        self._write_timing_report(out)

    def _write_timing_report(self, out: Path) -> None:
        """Write the phase breakdown beside the output, and only when the setting asks for it."""
        timing = getattr(self, "_timing", None)
        if timing is None or not tunables.get("output.timing_report"):
            return
        target = out.with_name(f"{out.stem}.timing.html")
        try:
            written = timing.write_html(target)
        except OSError as exc:
            self.status.emit(UIStrings.get("FEED_TIMING_FAILED").format(error=exc))
            return
        self.status.emit(UIStrings.get("FEED_TIMING_WRITTEN").format(name=written.name))

    def _emit_timeout(self, timeout: float) -> None:
        # Sağlayıcıya uygulanan zaman aşımını UI'a bildirir / Reports the timeout applied to the provider
        self.batch_timeout.emit(timeout)

    def _make_finalizer(self, config: JobConfig, provider=None) -> DocumentFinalizer:
        """The write-back path lives in DocumentFinalizer; this wires the worker's signals in."""
        return DocumentFinalizer(
            config,
            on_status=self.status.emit,
            on_job_stats=self.job_stats.emit,
            on_finished=self.finished_ok.emit,
            fit_pass=lambda d, s: self._fit_pdf_pass(d, s, config, provider),
            box_crushed=lambda: self._box_crushed,
            started_at=self._started_at,
            on_flagged=self._set_flagged,
        )

    def _set_flagged(self, flagged: int) -> None:
        """The finalizer counts the flagged segments; the timing report shows them."""
        if getattr(self, "_timing", None) is not None:
            self._timing.flagged = flagged

    def _finalize_document(
        self,
        doc: Document,
        translated: list[Segment],
        src: Path,
        out: Path,
        config: JobConfig,
        provider=None,
        phases: PhaseTimer | None = None,
    ) -> None:
        """Delegate to DocumentFinalizer: writing, verification and stats live there now."""
        self._make_finalizer(config, provider).finalize(
            doc, translated, src, out, provider=provider, phases=phases
        )

    def _verify(self, doc, translated, src: Path, out: Path, config: JobConfig, provider=None,
                source_slice: Path | None = None):
        """Delegate to DocumentFinalizer.verify."""
        return self._make_finalizer(config, provider).verify(
            doc, translated, src, out, config, provider, source_slice=source_slice
        )

    def _count_box_crushed(self) -> None:
        """One more block whose box, not its text, needs a look. The runner calls this."""
        self._box_crushed += 1

    def _collect_stats(self, translated: list[Segment]) -> dict:
        """Delegate to DocumentFinalizer.collect_stats."""
        return self._make_finalizer(self._config).collect_stats(translated)

    def _fit_pdf_pass(
        self, doc: Document, segments: list[Segment], config: JobConfig, provider=None
    ) -> None:
        """Delegate to FitPassRunner: the fitting pass lives there now, not in this class."""
        FitPassRunner(
            config,
            on_status=self.status.emit,
            on_progress=self.progress.emit,
            on_progress_detailed=self.progress_detailed.emit,
            on_box_crushed=self._count_box_crushed,
        ).run(doc, segments, provider=provider)
