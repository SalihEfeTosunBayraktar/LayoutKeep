"""The PDF fitting pass, split out of TranslationWorker.

The worker had grown past 490 lines and most of it was this: asking the provider for shorter or
longer renderings inside a character budget, applying the shared write-back and reporting a live
counter. It lives here now, with the worker's signals arriving as plain callbacks, so the class
holds no Qt state of its own - it is the fit pass, not the worker.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from layoutkeep.core import review, tunables
from layoutkeep.core.docir import Document, Segment
from layoutkeep.ui.job import JobConfig

__all__ = ["FitPassRunner"]


class FitPassRunner:
    """Runs the shared two-directional PDF fitting pass (mirrors cli._fit_pdf).

    The retranslate callback asks the real provider for a shorter/longer rendering within
    a character budget; the write-back (text, scale, review flag) is shared pdf_pass code
    so the GUI applies exactly what the CLI applies.
    """

    def __init__(
        self,
        config: JobConfig,
        *,
        on_status: Callable[[str], None],
        on_progress: Callable[[int, int], None],
        on_progress_detailed: Callable[[int, int, int, int, float, str], None],
        on_box_crushed: Callable[[], None],
    ) -> None:
        self._config = config
        self._on_status = on_status
        self._on_progress = on_progress
        self._on_progress_detailed = on_progress_detailed
        self._on_box_crushed = on_box_crushed

    def run(self, doc: Document, segments: list[Segment], provider=None) -> None:
        """Fit every translated block, writing text, scale and review flags back onto them."""
        from layoutkeep.fitting import FitMode
        from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass

        config = self._config
        # Imported lazily: worker.py imports this module, so a top-level import would cycle. The
        # glossary helpers live there too and move with them in a later step.
        from layoutkeep.ui.worker import (
            GlossaryUnreadableError,
            _build_provider,
            load_glossary_terms,
        )

        if provider is None:
            provider, _memory, glossary_terms = _build_provider(config)
        else:
            # The worker already built a provider (the normal path); the fit pass still needs the
            # glossary, because a shorter rendering asked for here must obey the same terms.
            try:
                glossary_terms = load_glossary_terms(config.glossary_path)
            except GlossaryUnreadableError:
                glossary_terms = None

        def retranslate(segment: Segment, budget: int) -> str:
            segment.max_len = budget
            again = provider.translate(
                [segment],
                src_lang=config.source_lang,
                tgt_lang=config.target_lang,
                glossary=glossary_terms,
            )
            return again[0].target if again and again[0].target else segment.target

        def fetch_many(pairs: list[tuple[Segment, int]]) -> dict[tuple[str, int], str]:
            """A whole round of shortenings in ONE request, keyed by (block id, budget).

            The batches are copies: the fit mutates `max_len` as it tightens a budget, and the batch
            must carry the budget it was asked for rather than whatever the last round left behind.
            """
            if not pairs:
                return {}
            batch = [replace(segment, max_len=budget) for segment, budget in pairs]
            again = provider.translate(
                batch,
                src_lang=config.source_lang,
                tgt_lang=config.target_lang,
                glossary=glossary_terms,
            )
            answers: dict[tuple[str, int], str] = {}
            for (segment, budget), reply in zip(pairs, again, strict=False):
                if reply is not None and reply.target:
                    answers[(segment.block_id, budget)] = reply.target
            return answers

        # The fit asks the model for a shorter rendering per overflowing box, and on a long run this
        # is where most of the time goes (measured: 39s of 65s on a ten-page paper). It announces
        # itself and reports its own counter, so the card says "fitting" with a live number instead
        # of sitting on "translating 1553/1553" while the run is nowhere near done.
        self._on_status("fitting")
        fit_total = sum(1 for segment in segments if segment.translated)
        fit_chars = sum(len(segment.target or "") for segment in segments) or 1
        fit_state = {"done": 0, "chars": 0, "started": time.monotonic()}

        def on_fitted(seg: Segment, block, result) -> None:
            fit_state["done"] += 1
            fit_state["chars"] += len(seg.target or "")
            if fit_total:
                spent = max(0.001, time.monotonic() - fit_state["started"])
                self._on_progress(fit_state["done"], fit_total)
                self._on_progress_detailed(
                    fit_state["done"],
                    fit_total,
                    fit_state["chars"],
                    fit_chars,
                    fit_state["done"] / spent,
                    "",
                )
            # fit_segment is pure - it reports what would fit. Writing the result back is ours.
            seg.target = result.text
            if result.needs_review:
                seg.needs_review = True
                if result.review_reason == review.BOX_CRUSHED:
                    # The box, not the text: say so in the interface's own language, and count it
                    # for the completion screen (the engine reports a key, the UI owns the words).
                    seg.review_reason = "REVIEW_BOX_CRUSHED"
                    self._on_box_crushed()
                else:
                    seg.review_reason = "REVIEW_FIT_FAILED"
                block.needs_review = True
                block.review_reason = seg.review_reason
            apply_scale(block, result.scale)

        fit_pdf_pass(
            doc,
            segments,
            retranslate=retranslate,
            fetch_many=fetch_many if bool(tunables.get("fitting.batched_requests")) else None,
            mode=FitMode.REFLOW if tunables.get("fitting.reflow") else FitMode.STRICT,
            target_lang=config.target_lang,
            on_fitted=on_fitted,
        )
