"""Finishing a run: the write-back, the verification pass and the numbers the screen reports.

Split out of TranslationWorker, which had grown past 490 lines. The worker still owns the run -
the provider loop, pause and cancel - and hands the finished document to this class, which writes
it, verifies it, repairs what it can and reports the figures. Everything it needs from the worker
arrives as a callback, so it holds no Qt state of its own.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from layoutkeep.core.docir import Document, Segment, apply_segments, save_project
from layoutkeep.core.timing import PhaseTimer, TimingReport
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.strings import UIStrings

__all__ = ["DocumentFinalizer"]


class DocumentFinalizer:
    """Writes the translated document, verifies it and collects the run's figures."""

    def __init__(
        self,
        config: JobConfig,
        *,
        on_status: Callable[[str], None],
        on_job_stats: Callable[[dict], None],
        on_finished: Callable[[str], None],
        fit_pass: Callable[[Document, list[Segment]], None],
        box_crushed: Callable[[], int],
        started_at: float | None,
        on_flagged: Callable[[int], None],
    ) -> None:
        self._config = config
        self._on_status = on_status
        self._on_job_stats = on_job_stats
        self._on_finished = on_finished
        self._fit_pass = fit_pass
        self._box_crushed = box_crushed
        self._started_at = started_at
        self._on_flagged = on_flagged

    def finalize(
        self,
        doc: Document,
        translated: list[Segment],
        src: Path,
        out: Path,
        provider=None,
        phases: PhaseTimer | None = None,
    ) -> None:
        """Everything from the last reply to the finished file, in the CLI's order."""
        # Imported lazily: worker.py imports this module, so a top-level import would cycle.
        from layoutkeep.ui.worker import _output_document, _source_slice, _write_document

        config = self._config
        from layoutkeep.providers.passthrough import flag_passthrough, flag_untranslated
        from layoutkeep.providers.retry import retry_untranslated

        # A run started from a test or a script may not want timings; a throwaway timer keeps every
        # `with phases.phase(...)` below valid without a branch on each one.
        phases = phases or PhaseTimer(TimingReport())
        flagged = sum(1 for segment in translated if segment.needs_review)
        self._on_flagged(flagged)
        # Same order as the CLI, and for the same reason: a segment with no reply is usually one
        # the parser could not line up with its batch, so it is asked for again before anything
        # is flagged. What is still missing afterwards keeps its SOURCE text in the output, so
        # it has to reach the review queue rather than pass as translated.
        if provider is not None:
            # Its own phase: this step re-asks the model for the segments it could not parse, and on
            # a local model that is minutes per request. It used to be invisible in the timing report,
            # which made a run's total look wrong by exactly this much (measured: 300 s on one arm).
            with phases.phase("recover", f"{sum(1 for s in translated if not s.translated)} missing"):
                recovered = retry_untranslated(
                    provider,
                    translated,
                    src_lang=config.source_lang,
                    tgt_lang=config.target_lang,
                )
            if recovered:
                self._on_status(f"recovered {recovered} untranslated segments")

        flag_passthrough(translated)
        flag_untranslated(translated)

        # One source text, one translation across the document (core/repeats.py): the provider
        # already shares repeated text, and this makes agree what a memory entry, an earlier run
        # or a repair round left worded differently.
        from layoutkeep.core.repeats import unify_repeats

        with phases.phase("unify", "repeated sources"):
            unified = unify_repeats(translated, config.target_lang)
        if unified["rewritten"]:
            self._on_status(UIStrings.get("STATUS_REPEATS_UNIFIED").format(n=unified["rewritten"]))

        # PDF: translated text must fit its original boxes, exactly like the CLI fits it
        # (the GUI drifting from the CLI here is a bug - both run the same pdf_pass).
        if src.suffix.lower() == ".pdf":
            with phases.phase("fit", "PDF pass"):
                self._fit_pass(doc, translated)

        self._on_status("applying translation")
        with phases.phase("apply", f"{len(translated)} segments"):
            apply_segments(doc, translated)

        self._on_status("writing output")
        output_doc, range_pages = _output_document(doc, config)
        slice_path = None
        if range_pages is not None:
            slice_path = _source_slice(src, range_pages, out.with_suffix(".range-src.pdf"))
            self._on_status(f"output holds the selected {len(range_pages)} pages")
        # The PDF writer renders *from the source file*, page by page, so a range is only honoured
        # when the writer is handed the sliced source: dropping pages from the document alone left
        # the whole book in the output (the pages the range left out simply went untouched).
        write_source = slice_path or src
        try:
            with phases.phase("write", out.suffix.lower() or "output"):
                _write_document(output_doc, write_source, out)
            with phases.phase("verify", "lossless audit"):
                verification = self.verify(
                    output_doc, translated, write_source, out, config, provider,
                    source_slice=slice_path,
                )
        finally:
            if slice_path is not None:
                slice_path.unlink(missing_ok=True)

        # Çift dilli çıktı, doğrulamadan SONRA yazılır: doğrulama asıl (tek dilli) PDF'i denetler
        # ve gerekirse yeniden yazar; çift dilli dosya onun yanına, son hâlinden üretilir.
        dual_mode = getattr(config, "dual_mode", "") or ""
        if dual_mode and src.suffix.lower() == ".pdf" and out.suffix.lower() == ".pdf":
            from layoutkeep.writers.dual_pdf import compose_dual

            dual_path = out.with_name(f"{out.stem}.dual{out.suffix}")
            self._on_status("writing bilingual copy")
            composed = compose_dual(src, out, dual_path, dual_mode)
            self._on_status(f"bilingual copy: {composed} pages ({dual_mode})")

        project_path = config.project_path or str(out.with_suffix(".lkproj"))
        save_project(doc, project_path)
        stats = self.collect_stats(translated)
        stats["verify_repaired"] = verification.repaired
        stats["verify_remaining"] = dict(verification.remaining)
        self._on_job_stats(stats)
        self._on_finished(project_path)

    def verify(
        self,
        doc,
        translated,
        src: Path,
        out: Path,
        config: JobConfig,
        provider=None,
        source_slice: Path | None = None,
    ):
        """The CLI's verification pass (layoutkeep/verify.py): check what was written, ask again
        for what a translation lost, flag the rest - so the review queue shows every loss.

        `source_slice` is the selected pages of the source when the output holds a page range:
        the pass pairs source page N with output page N, and a subset output has to be checked
        against the matching subset of the source, not against the whole book.
        """
        from layoutkeep.providers.retry import retry_untranslated
        from layoutkeep.ui.worker import _write_document
        from layoutkeep.verify import verify_and_repair

        self._on_status("verifying output")
        pdf_to_pdf = src.suffix.lower() == ".pdf" and out.suffix.lower() == ".pdf"
        compare_against = source_slice or (src if pdf_to_pdf else None)

        def ask_again(again) -> int:
            return retry_untranslated(
                provider, again, src_lang=config.source_lang, tgt_lang=config.target_lang
            )

        report = verify_and_repair(
            doc,
            translated,
            target_lang=config.target_lang,
            write=lambda: _write_document(doc, src, out),
            source_pdf=compare_against,
            output_pdf=out if compare_against is not None else None,
            ask_again=ask_again if provider is not None else None,
            refit=(
                (lambda again: self._fit_pass(doc, again))
                if src.suffix.lower() == ".pdf" else None
            ),
        )
        if report.repaired:
            self._on_status(f"verification mended {report.repaired} segments")
        return report

    def collect_stats(self, translated: list[Segment]) -> dict:
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
            "flagged_box_crushed": self._box_crushed(),
            "chars": chars,
            "elapsed_s": elapsed,
            "chars_per_second": (chars / elapsed) if elapsed > 0 else 0.0,
            "clean_ratio": ((total - flagged) / total) if total else 0.0,
        }
