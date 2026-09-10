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
    apply_segments,
    save_project,
    segments_from_document,
)
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.strings import UIStrings

#: How many segments the worker hands the provider at a time.
#:
#: This exists so cancellation and pause have somewhere to land: the flags are checked between
#: chunks, never mid-request. It is NOT the request size - the provider sizes its own requests
#: adaptively (providers/batching.AdaptiveBatchSize: start at 1, grow while replies come back
#: valid, shrink on BatchTooLargeError, ceiling 20).
#:
#: It used to be 4, which silently capped that adaptation at 4 and stopped it ever finding a
#: model's real ceiling - measured at 5 for the models tried here, and a model that could
#: manage more never got the chance. The CLI hands over every segment at once and does not
#: have this problem, so the two disagreed; CONTRACT-wise the GUI drifting from the CLI is a
#: bug. Matching the adaptive ceiling lets the provider breathe while keeping cancellation
#: granular enough to feel responsive.
_BATCH_SIZE = 20

_FIRST_BATCH_BASE_TIMEOUT_S = 240.0
_WARM_BATCH_BASE_TIMEOUT_S = 15.0
_DEFAULT_CHARS_PER_SECOND = 12.0
_MIN_BATCH_TIMEOUT_S = 30.0
_MAX_BATCH_TIMEOUT_S = 900.0


def _batch_timeout(chars: int, *, is_first: bool, chars_per_second: float | None) -> float:
    base = _FIRST_BATCH_BASE_TIMEOUT_S if is_first else _WARM_BATCH_BASE_TIMEOUT_S
    rate = chars_per_second or _DEFAULT_CHARS_PER_SECOND
    estimate = base + chars / rate
    return max(_MIN_BATCH_TIMEOUT_S, min(_MAX_BATCH_TIMEOUT_S, estimate))


def _set_provider_timeout(provider, seconds: float) -> None:
    target = provider
    while (inner := getattr(target, "inner", None)) is not None:
        target = inner
    if hasattr(target, "timeout"):
        target.timeout = seconds


def _read_document(path: Path) -> Document:
    from layoutkeep.writers.converter import read_any_document

    return read_any_document(path)


def _write_document(doc: Document, source: Path, out: Path) -> list[Path]:
    from layoutkeep.writers.converter import write_any_document

    return write_any_document(doc, source, out)


def _build_provider(config: JobConfig):
    if config.provider.kind == "fake":
        from layoutkeep.providers.fake import FakeProvider

        provider, model_id = FakeProvider(), "fake"
    elif config.provider.kind == "deepl":
        from layoutkeep.providers.deepl import DeepLProvider

        provider = DeepLProvider(
            config.provider.api_key or "",
            base_url=config.provider.base_url or None,
            timeout=config.provider.timeout or 60.0,
        )
        # The key picks the host, so that is what identifies the model for the memory.
        model_id = f"deepl:{provider.host}"
    else:
        from layoutkeep.providers.openai_compat import OpenAICompatProvider

        provider = OpenAICompatProvider(
            base_url=config.provider.base_url,
            model=config.provider.model,
            api_key=config.provider.api_key,
        )
        model_id = f"{config.provider.base_url}:{config.provider.model}"

    from layoutkeep.providers.protected import ProtectedProvider

    if not config.memory_path:
        return ProtectedProvider(provider), None

    from layoutkeep.providers.cached import CachedProvider
    from layoutkeep.providers.memory import TranslationMemory

    memory = TranslationMemory(config.memory_path)
    return ProtectedProvider(CachedProvider(provider, memory, model_id)), memory


# ---------------------------------------------------------------------------
# Translation loop helpers (module-level, so the worker class stays focused on
# QThread/signal plumbing). They receive the worker instance to emit signals.
# ---------------------------------------------------------------------------


def _segment_preview(source_text: str) -> str:
    """Build the short single-line preview shown next to the active segment."""
    clean = source_text.strip().replace("\n", " ")
    return clean[:77] + "…" if len(clean) > 80 else clean


def _timeout_error_message(base_url: str, timeout: float) -> str:
    return (
        f"Sunucu ({base_url}) {timeout:.0f} saniye içinde yanıt vermedi.\n"
        "Büyük bir yerel model yüklenmesi dakikalar sürebilir; sunucu tamamen hazır "
        "olduktan sonra tekrar deneyin, ya da Sağlayıcı Ayarları'ndan zaman aşımını "
        "elle yükseltin."
    )


def _connection_error_message(base_url: str, exc: Exception) -> str:
    return (
        f"{base_url} adresine ulaşılamıyor: {exc}\n"
        "LM Studio (1234 portu) veya Ollama (11434 portu) sunucusunun çalıştığından "
        "ve sunucu modunun etkin olduğundan emin olun."
    )


def _run_translation_loop(
    worker: TranslationWorker,
    provider,
    memory,
    segments: list[Segment],
    total: int,
    total_chars: int,
    *,
    source_lang: str,
    target_lang: str,
) -> list[Segment] | None:
    """Translate `segments` in batches; returns None if cancelled or a batch errored."""
    from layoutkeep.providers.batching import BatchProgress

    worker.status.emit("translating")
    translated: list[Segment] = []
    chars_per_second: float | None = None
    done_chars = 0

    chunk_size = tunables.get("batch.chunk_size")
    for batch_index, start in enumerate(range(0, total, chunk_size)):
        if worker._cancelled:
            worker.status.emit("cancelled")
            return None

        if not worker._pause_event.is_set():
            # Reached the boundary: now it really is paused, not merely asked to.
            worker.status.emit(UIStrings.STATUS_PAUSED)
        while not worker._pause_event.is_set():
            if worker._cancelled:
                worker.status.emit("cancelled")
                return None
            time.sleep(0.1)

        batch = segments[start : start + chunk_size]
        worker.active_segment.emit(start + 1, _segment_preview(batch[0].source))
        batch_chars = sum(len(s.source) for s in batch)
        timeout = _compute_batch_timeout(
            provider,
            worker._config.provider.timeout,
            batch_chars,
            is_first=batch_index == 0,
            chars_per_second=chars_per_second,
        )
        _set_provider_timeout(provider, timeout)
        worker.batch_timeout.emit(timeout)

        hits_before = memory.stats()["hits"] if memory is not None else 0
        started = time.monotonic()
        base_done = len(translated)
        base_chars = done_chars

        def _sub_progress(
            bp: BatchProgress,
            b_done: int = base_done,
            b_chars: int = base_chars,
        ) -> None:
            curr_done = b_done + bp.segments_done
            curr_chars = b_chars + bp.chars_done
            worker.progress.emit(curr_done, total)
            worker.progress_detailed.emit(curr_done, total, curr_chars, total_chars, 0.0, "")

        try:
            result = provider.translate(
                batch,
                src_lang=source_lang,
                tgt_lang=target_lang,
                on_progress=_sub_progress,
            )
        except TimeoutError:
            worker.failed.emit(_timeout_error_message(worker._config.provider.base_url, timeout))
            return None
        except OSError as exc:
            worker.failed.emit(_connection_error_message(worker._config.provider.base_url, exc))
            return None

        elapsed = time.monotonic() - started
        hit_this = memory is not None and memory.stats()["hits"] > hits_before
        # Her gerçek (memory-hit olmayan) batch'te hızı güncelle: hem timeout hesabı hem UI
        # hız göstergesi için. İlk ölçüme kilitlenmek yanlış - soğuk model yüklemesi ilk
        # batch'i her zaman yavaşlatır ve sonraki batch'ler daha hızlıdır.
        measured = batch_chars > 0 and elapsed > 0 and not hit_this
        if measured:
            chars_per_second = batch_chars / elapsed

        translated.extend(result)
        # The progress screen shows source and translation side by side; until now only the
        # source was emitted, so the right-hand panel had nothing to draw.
        for produced in result:
            if produced.target:
                worker.segment_translated.emit(
                    _segment_preview(produced.source), _segment_preview(produced.target)
                )
        worker.review_flags.emit(
            sum(1 for seg in translated if seg.needs_review), len(translated)
        )
        done_chars += batch_chars
        # UI'a giden hız: bu batch'in ölçülen hızı (batch_chars / elapsed), kümülatif değil.
        # Memory hit batch'leri ~0 saniyede döner - onların "hızı" gerçek değildir, 0.0
        # gönder (EtaCalculator 0.0'ı ölçüm yok sayar).
        rate = chars_per_second if measured else 0.0
        worker.progress.emit(len(translated), total)
        worker.progress_detailed.emit(len(translated), total, done_chars, total_chars, rate, "")
        if memory is not None:
            st = memory.stats()
            worker.memory_stats.emit(st["hits"], st["hits"] + st["misses"])

    return translated


def _compute_batch_timeout(
    provider, configured_timeout: float | None, chars: int, *, is_first: bool, chars_per_second: float | None
) -> float:
    """Compute per-batch timeout and push it through any provider wrappers."""
    if configured_timeout:
        timeout = configured_timeout
    else:
        timeout = _batch_timeout(chars, is_first=is_first, chars_per_second=chars_per_second)
    _set_provider_timeout(provider, timeout)
    return timeout


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

        self.status.emit("reading document")
        try:
            doc = _read_document(src)
        except FileNotFoundError as exc:
            # A1: eksik/okunamayan girdi traceback degil, tek cumle / missing input → one line
            self.failed.emit(str(exc))
            return
        except ValueError as exc:
            self.failed.emit(str(exc))
            return
        doc.source_lang = config.source_lang
        doc.target_lang = config.target_lang

        segments = self._filter_segments(doc, config)
        total = len(segments)
        if total == 0:
            self.failed.emit("Belgede çevrilebilir metin bulunamadı.")
            return

        total_chars = sum(len(s.source) for s in segments)
        provider, memory = _build_provider(config)
        self.progress.emit(0, total)
        self.progress_detailed.emit(0, total, 0, total_chars, 0.0, "")

        translated = _run_translation_loop(
            self,
            provider,
            memory,
            segments,
            total,
            total_chars,
            source_lang=config.source_lang,
            target_lang=config.target_lang,
        )
        if translated is None:
            return

        self._finalize_document(doc, translated, src, out, config, provider)

    def _filter_segments(self, doc: Document, config: JobConfig) -> list[Segment]:
        # Belgeden segmentleri çıkarır ve aralığa göre filtreler / Extracts and filters segments
        segments = segments_from_document(doc)
        if config.page_range and doc.pages:
            from layoutkeep.core.range_helper import block_ids_for_pages, parse_page_range

            selected_pages = parse_page_range(config.page_range, len(doc.pages))
            allowed = block_ids_for_pages(doc, selected_pages)
            segments = [seg for seg in segments if seg.block_id in allowed]
        return segments

    def _emit_timeout(self, timeout: float) -> None:
        # Sağlayıcıya uygulanan zaman aşımını UI'a bildirir / Reports the timeout applied to the provider
        self.batch_timeout.emit(timeout)

    def _finalize_document(
        self,
        doc: Document,
        translated: list[Segment],
        src: Path,
        out: Path,
        config: JobConfig,
        provider=None,
    ) -> None:
        from layoutkeep.providers.passthrough import flag_passthrough

        flag_passthrough(translated)

        # PDF: translated text must fit its original boxes, exactly like the CLI fits it
        # (the GUI drifting from the CLI here is a bug - both run the same pdf_pass).
        if src.suffix.lower() == ".pdf":
            self._fit_pdf_pass(doc, translated, config, provider)

        self.status.emit("applying translation")
        apply_segments(doc, translated)

        self.status.emit("writing output")
        _write_document(doc, src, out)

        project_path = config.project_path or str(out.with_suffix(".lkproj"))
        save_project(doc, project_path)
        self.job_stats.emit(self._collect_stats(translated))
        self.finished_ok.emit(project_path)

    def _collect_stats(self, translated: list[Segment]) -> dict:
        """Figures the completion screen reports, all counted rather than estimated.

        `clean_ratio` is the share of segments that finished without raising a review flag.
        It is presented as layout fidelity because every reason a segment gets flagged - a
        translation that would not fit its box, lost inline styling, a dropped protected
        value, text handed back untranslated - is a way the output departs from the original.
        """
        total = len(translated)
        done = sum(1 for s in translated if s.target)
        flagged = sum(1 for s in translated if s.needs_review)
        chars = sum(len(s.target or "") for s in translated)
        elapsed = (time.monotonic() - self._started_at) if self._started_at else 0.0
        return {
            "segments_total": total,
            "segments_done": done,
            "segments_flagged": flagged,
            "chars": chars,
            "elapsed_s": elapsed,
            "chars_per_second": (chars / elapsed) if elapsed > 0 else 0.0,
            "clean_ratio": ((total - flagged) / total) if total else 0.0,
        }

    def _fit_pdf_pass(
        self, doc: Document, segments: list[Segment], config: JobConfig, provider=None
    ) -> None:
        """Run the shared two-directional PDF fitting pass (mirrors cli._fit_pdf).

        The retranslate callback asks the real provider for a shorter/longer rendering within
        a character budget; the write-back (text, scale, review flag) is shared pdf_pass code
        so the GUI applies exactly what the CLI applies.
        """
        from layoutkeep.fitting import FitMode
        from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass

        if provider is None:
            provider, _memory = _build_provider(config)

        def retranslate(segment: Segment, budget: int) -> str:
            segment.max_len = budget
            again = provider.translate(
                [segment],
                src_lang=config.source_lang,
                tgt_lang=config.target_lang,
            )
            return again[0].target if again and again[0].target else segment.target

        def on_fitted(seg: Segment, block, result) -> None:
            # fit_segment is pure - it reports what would fit. Writing the result back is ours.
            seg.target = result.text
            if result.needs_review:
                seg.needs_review = True
                seg.review_reason = "çeviri kutuya sığmadı, küçültme yetmedi"
                block.needs_review = True
                block.review_reason = seg.review_reason
            apply_scale(block, result.scale)

        fit_pdf_pass(
            doc,
            segments,
            retranslate=retranslate,
            mode=FitMode.STRICT,
            target_lang=config.target_lang,
            on_fitted=on_fitted,
        )
