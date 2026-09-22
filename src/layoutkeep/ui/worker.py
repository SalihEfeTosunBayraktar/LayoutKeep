"""Background translation worker.

Runs entirely on a QThread so the main thread never blocks. It only calls into
`layoutkeep.core` and `layoutkeep.providers` - the same functions `cli.py` calls - and never
reimplements translation, fitting or I/O logic (see docs/CONTRACT.md, D1/D2).
"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    Document,
    Segment,
    segments_from_document,
)
from layoutkeep.core.timing import PhaseTimer, TimingReport
from layoutkeep.ui.doc_glossary import DocGlossaryBuilder
from layoutkeep.ui.document_finalizer import DocumentFinalizer
from layoutkeep.ui.fit_pass_runner import FitPassRunner
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.topic_map import TopicMapBuilder
from layoutkeep.ui.translation_loop import _run_translation_loop

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
    # The first batch pays for a cold model load, and how long that takes is a property of the
    # machine, not of this code - so it is a setting (`timeout.first_batch_s`), with the constant
    # as the fallback. It used to be a declared-but-unread switch: visible in the dialog, wired to
    # nothing.
    first = tunables.get("timeout.first_batch_s")
    base = float(first if is_first and first else _FIRST_BATCH_BASE_TIMEOUT_S if is_first else _WARM_BATCH_BASE_TIMEOUT_S)
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
    from layoutkeep.ocr.layout_detector import load_detector
    from layoutkeep.writers.converter import read_any_document

    # The local layout model when it is installed, as the CLI reads (cli._layout_detector): the
    # desktop application read every page without it, although the campaign measured every result
    # with it.
    return read_any_document(path, layout=load_detector())


def _write_document(doc: Document, source: Path, out: Path) -> list[Path]:
    from layoutkeep.writers.converter import write_any_document

    return write_any_document(doc, source, out)


def _output_document(doc: Document, config) -> tuple[Document, set[int] | None]:
    """What the range promises, made true: the written file holds the selected pages.

    WHY THIS EXISTS: a page range used to narrow only what was *translated*, so choosing
    "40-60" produced a translation of those pages inside a copy of the whole book - reported as
    "shouldn't it output only the range I selected?". The project still keeps every page (the
    reviewer needs the rest, and re-exporting must not silently shorten the document), so the
    range is applied to a copy used for writing, not to the document that is saved.

    Sayfa aralığı artık çıktıyı da daraltır; kaydedilen proje belgenin tamamını korur.
    """
    if not (config.page_range and doc.pages):
        return doc, None

    from layoutkeep.core.range_helper import filter_document_by_pages, parse_page_range

    selected = parse_page_range(config.page_range, len(doc.pages))
    if len(selected) >= len(doc.pages):
        return doc, None

    subset = filter_document_by_pages(doc, selected)
    # The verification pass pairs source page N with output page N through `source_ref`, so the
    # kept pages are renumbered to their position inside the slice. They are deep-copied first:
    # filter_document_by_pages shares the Page objects with the project's document, and
    # renumbering those in place would corrupt the saved project.
    pages = []
    for index, page in enumerate(subset.pages):
        copied = copy.deepcopy(page)
        copied.source_ref = str(index)
        pages.append(copied)
    return replace(subset, pages=pages), selected


def _source_slice(src: Path, selected: set[int], destination: Path) -> Path | None:
    """The selected pages of the source, as their own PDF, so verification compares like with like.

    A subset output cannot be checked against the full source: page 1 of the output is not page 1
    of the book, and every loss rule would read the wrong pair.
    """
    if src.suffix.lower() != ".pdf":
        return None
    import pymupdf

    with pymupdf.open(str(src)) as source:
        out = pymupdf.open()
        try:
            for number in sorted(selected):
                if 1 <= number <= source.page_count:
                    out.insert_pdf(source, from_page=number - 1, to_page=number - 1)
            if out.page_count in (0, source.page_count):
                return None
            out.save(str(destination))
        finally:
            out.close()
    return destination


def load_glossary_terms(path: str | None) -> dict[str, str] | None:
    """Read a JSON glossary, or None when no file is configured.

    A broken file is not a reason to fail the job: it is reported by the caller and the run goes
    on without the glossary, which is the same document the user would have got before.
    """
    if not path:
        return None
    from layoutkeep.providers.glossary import Glossary

    try:
        glossary = Glossary.load(path)
    except (OSError, ValueError) as exc:
        # A typo in a path or a hand-edited JSON file must not end a two-hour run before it
        # starts; the caller reports it and the document is translated as it would have been.
        raise GlossaryUnreadableError(path, str(exc)) from exc
    return glossary.terms or None


class GlossaryUnreadableError(Exception):
    """The configured glossary file could not be read; the run continues without it."""


def _glossary_fingerprint(terms: dict[str, str]) -> str:
    """Short hash of a glossary, folded into the memory key.

    WHY THIS EXISTS: the translation memory is keyed by (source, languages, model). A glossary
    changes what the model is asked for, so a translation produced before the term policy existed
    would otherwise be served straight back - the exact case the memory's own warning describes.
    """
    payload = chr(0).join(f"{k}={v}" for k, v in sorted(terms.items())).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


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

    from layoutkeep.providers.dedupe import DedupeProvider
    from layoutkeep.providers.protected import ProtectedProvider

    try:
        terms = load_glossary_terms(config.glossary_path)
    except GlossaryUnreadableError:
        terms = None  # the job runs without it; the settings dialog is where this is fixed
    if terms:
        model_id = f"{model_id}|gloss:{_glossary_fingerprint(terms)}"

    if not config.memory_path:
        return ProtectedProvider(DedupeProvider(provider)), None, terms

    from layoutkeep.providers.cached import CachedProvider
    from layoutkeep.providers.memory import TranslationMemory

    memory = TranslationMemory(config.memory_path)
    return ProtectedProvider(CachedProvider(DedupeProvider(provider), memory, model_id)), memory, terms


# ---------------------------------------------------------------------------
# Translation loop helpers (module-level, so the worker class stays focused on
# QThread/signal plumbing). They receive the worker instance to emit signals.
# ---------------------------------------------------------------------------


def _timeout_error_message(base_url: str, timeout: float) -> str:
    return UIStrings.get("ERROR_TIMEOUT").format(url=base_url, s=f"{timeout:.0f}")


def _connection_error_message(base_url: str, exc: Exception) -> str:
    return UIStrings.get("ERROR_CONNECTION").format(url=base_url, exc=exc)


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
        try:
            with phases.phase("read", src.suffix.lower() or "input"):
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

        # Kaynakça koruması (ayar açıksa) bölümlemeden ÖNCE gelir: işaretlenen blok çevrilebilir
        # sayılmaz, yani modele hiç gitmez. Aynı ayarı komut satırı da okur.
        if tunables.get("translation.preserve_references"):
            from layoutkeep.core.reference import tag_bibliography_blocks

            tagged = tag_bibliography_blocks(doc, preserve=True)
            if tagged:
                self.status.emit(f"references: {tagged} bibliography blocks preserved untouched")

        provider, memory, glossary_terms = _build_provider(config)

        # Belge sözlüğü (ayar açıksa) bölümlemeden ÖNCE gelir (D-007): terim listesi bu koşunun her
        # isteğine, sığdırmasına ve bellek anahtarına girer; zincir sözlük yazıldıktan SONRA kurulur.
        if bool(tunables.get("translation.auto_glossary")):
            with phases.phase("glossary", "before the translation"):
                config, merged = DocGlossaryBuilder(on_status=self.status.emit).build(
                    doc, out, provider, config
                )
                if merged:
                    glossary_terms = merged
                    provider, memory, _ = _build_provider(config)

        # Konu haritası (ayar açıksa) bölümlemeden ÖNCE gelir: segmentler kurulurken her blok kendi
        # anahtar kelimesini haritadan okur, yani dosya o an yerinde olmalı.
        if bool(tunables.get("translation.keyword_map_auto")):
            with phases.phase("keyword map", "before the translation"):
                self._build_keyword_map(doc, out, provider)

        with phases.phase("segment", "segments in range"):
            segments = self._filter_segments(doc, config)
        # The map is only needed while the segments are built; put the user's own value back so a
        # run cannot leave their settings changed.
        if getattr(self, "_keyword_map_previous", None) is not None:
            tunables.set_value("translation.keyword_map_path", self._keyword_map_previous)
            self._keyword_map_previous = None
        total = len(segments)
        if total == 0:
            self.failed.emit(UIStrings.get("ERROR_NO_TEXT"))
            return

        # Karakter bütçesi çeviriden ÖNCE (D-011): modele ilk istekte 'max_len' olarak gider, yani
        # sığdırmanın tek tek düzeltmesi baştan azalır. PDF yoksa anlamsız - kutu geometrisi yok.
        prefit = str(tunables.get("translation.prefit_budget") or "")
        if src.suffix.lower() == ".pdf" and prefit:
            from layoutkeep.fitting.pdf_pass import budget_segments

            with phases.phase("budget", "per box"):
                filled = budget_segments(
                    doc,
                    segments,
                    target_lang=config.target_lang,
                    headroom=1.2 if prefit == "loose" else 1.0,
                )
            self.status.emit(f"character budgets: {filled} of {total} boxes ({prefit})")

        total_chars = sum(len(s.source) for s in segments)
        self.progress.emit(0, total)
        self.progress_detailed.emit(0, total, 0, total_chars, 0.0, "")

        with phases.phase("translate", f"{total} segments, {total_chars:,} chars"):
            translated = _run_translation_loop(
                self,
                provider,
                memory,
                segments,
                total,
                total_chars,
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                glossary=glossary_terms,
            )
        if translated is None:
            return

        self._finalize_document(doc, translated, src, out, config, provider, phases)
        self._write_timing_report(out)

    def _build_keyword_map(self, doc: Document, out: Path, provider) -> None:
        """Delegate to TopicMapBuilder: the map build lives there now."""
        target, previous = TopicMapBuilder(on_status=self.status.emit).build(doc, out, provider)
        self._keyword_map_previous = previous
        self._keyword_map_path = target
    def _write_timing_report(self, out: Path) -> None:
        """Write the phase breakdown beside the output, and only when the setting asks for it."""
        timing = getattr(self, "_timing", None)
        if timing is None or not tunables.get("output.timing_report"):
            return
        target = out.with_name(f"{out.stem}.timing.html")
        try:
            written = timing.write_html(target)
        except OSError as exc:
            self.status.emit(f"timing report could not be written: {exc}")
            return
        self.status.emit(f"timing report: {written.name}")

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
