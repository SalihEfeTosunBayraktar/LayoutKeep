"""Abstract translation provider (see docs/CONTRACT.md, D2).

This module and everything else under `providers/` is layout-blind: it knows `Segment`
and nothing else about the document's visual representation or the PDF/EPUB engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from layoutkeep.core.docir import Segment
from layoutkeep.providers.batching import ProgressCallback


class TranslationProvider(ABC):
    """Translates a batch of segments. Implementations must not reorder or drop segments.

    Callers match results back to source blocks by `Segment.block_id`, never by list position.
    """

    @abstractmethod
    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        """Translate `segments` from `src_lang` to `tgt_lang`.

        Returns one Segment per input segment, each with `block_id` unchanged and `target` set.
        A segment that could not be translated is returned with `needs_review=True` rather than
        being dropped or silently filled with the source text.

        `on_progress`, if given, is called after each internal batch a provider issues (see
        `providers/batching.py`) with a `BatchProgress` snapshot. Providers that make a single
        request for the whole call are free to ignore it or call it once at the end.
        """
        raise NotImplementedError
