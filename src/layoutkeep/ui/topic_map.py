"""Building the per-stretch topic map that a run can use before it translates.

Split out of TranslationWorker. The map is one chat call per stretch of the document, written
beside the output and pointed at only for this run; the class reports through a callback and
returns what it did, so the worker keeps no topic-map state of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from layoutkeep.core import tunables
from layoutkeep.core.docir import Document
from layoutkeep.providers.base import chat_callable

__all__ = ["TopicMapBuilder"]


class TopicMapBuilder:
    """Asks the model what each stretch of the document is about, once, before translating it.

    The file lands beside the output and is only pointed at for this run: the user's own value in
    'Konu haritası dosyası' is put back as soon as the segments have read the map. A model that
    does not answer leaves an empty map behind, which costs nothing - the segment builder reads
    what is there and ignores the rest.
    """

    def __init__(self, *, on_status: Callable[[str], None]) -> None:
        self._on_status = on_status

    def build(self, doc: Document, out: Path, provider) -> tuple[Path | None, str]:
        """Returns (map path or None, the setting's previous value) so the caller can restore it."""
        from layoutkeep.core.keywords import build_keyword_map, filled_entries, write_keyword_map

        # The chat call under the wrappers, never on the outermost object: a run hands over
        # ProtectedProvider(CachedProvider(DedupeProvider(provider))) and no decorator forwards
        # `_chat`, so asking the outside found nothing and the map was skipped on every real
        # provider - the case `providers/base.chat_callable` exists for.
        chat = chat_callable(provider)
        if chat is None:
            self._on_status("topic map skipped: this provider has no chat call")
            return None, ""
        self._on_status("building the topic map")

        def ask(system: str, user: str) -> str:
            return str(
                chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ]
                )
            )

        entries = build_keyword_map(doc, ask)
        target = write_keyword_map(entries, out.with_name(f"{out.stem}.keyword-map.json"))
        previous = str(tunables.get("translation.keyword_map_path") or "")
        tunables.set_value("translation.keyword_map_path", str(target))
        filled, words = filled_entries(entries)
        self._on_status(f"topic map: {filled}/{len(entries)} stretches, {words} keywords")
        return target, previous
