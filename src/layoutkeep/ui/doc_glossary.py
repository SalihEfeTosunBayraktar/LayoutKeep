"""The run's automatic glossary: the document's recurring terms, rendered once before it starts.

Split out of TranslationWorker, which has a line budget of its own (D-017). One chat call for the
whole document, the merged list written beside the output and pointed at for this run only.

The config the worker gets back is a copy (`dataclasses.replace`), so the user's own job config is
never edited and nothing has to be put back afterwards - the same promise the topic map keeps by
restoring the setting it borrowed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from layoutkeep.core.doc_glossary import build_doc_glossary, merge_glossaries, write_glossary
from layoutkeep.core.docir import Document
from layoutkeep.providers.base import chat_callable
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.strings import UIStrings

__all__ = ["DocGlossaryBuilder"]


class DocGlossaryBuilder:
    """Asks the model once for the document's terms and returns the config the rest of the run uses.

    The prompt, the fitting pass and the memory key all read the run's glossary through the config
    (`config.glossary_path`), so the merged list is handed to them in one move rather than in three.
    A provider with no chat call - DeepL, and anything else that only translates - is skipped, and
    so is a run whose model answers with nothing: both leave the run exactly as it would have been.
    """

    def __init__(self, *, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status

    def build(
        self,
        doc: Document,
        out: Path,
        provider,
        config: JobConfig,
    ) -> tuple[JobConfig, dict[str, str]]:
        """Returns (config pointing at the merged file, the merged terms), or the config as it came."""
        chat = chat_callable(provider)
        if chat is None:
            self._on_status(UIStrings.get("FEED_GLOSSARY_SKIPPED"))
            return config, {}
        self._on_status(UIStrings.get("FEED_GLOSSARY_ASKING"))

        def ask(system: str, user: str) -> str:
            return str(
                chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ]
                )
            )

        automatic = build_doc_glossary(
            doc,
            ask,
            source_lang=config.source_lang,
            target_lang=config.target_lang,
        )
        if not automatic:
            self._on_status(UIStrings.get("FEED_GLOSSARY_EMPTY"))
            return config, {}

        user = self._user_terms(config)
        merged = merge_glossaries(automatic, user)
        target = write_glossary(merged, out.with_name(f"{out.stem}.glossary.json"))
        self._on_status(UIStrings.get("FEED_GLOSSARY_BUILT").format(auto=len(automatic), user=len(user)))
        return replace(config, glossary_path=str(target)), merged

    @staticmethod
    def _user_terms(config: JobConfig) -> dict[str, str]:
        """The terms the user's own glossary file holds: those win where the two disagree."""
        # Imported lazily: worker.py imports this module, so a top-level import would cycle.
        from layoutkeep.ui.worker import GlossaryUnreadableError, load_glossary_terms

        try:
            return load_glossary_terms(config.glossary_path) or {}
        except GlossaryUnreadableError:
            # The unreadable file is already reported by the provider build; the run goes on with
            # the model's own terms rather than stopping for a path typo.
            return {}
