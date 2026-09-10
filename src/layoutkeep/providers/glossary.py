"""Terminology dictionary: injected into the translation prompt and verified afterwards.

File format: JSON, a flat {source_term: target_term} object. Chosen over TSV because the
glossary is exactly the dict[str, str] shape `TranslationProvider.translate` already takes
for its `glossary` parameter (see base.py / openai_compat.py) - JSON round-trips that shape
with no parsing ambiguity (TSV would need escaping rules for terms containing tabs/newlines,
which glossary entries occasionally do for phrasal terms).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from layoutkeep.core.docir import Segment


class Glossary:
    """A source-term -> target-term mapping, with source-side matching and target-side checks.

    Matching is case-aware (an exact-case term match, not casefolded) and word-boundary aware:
    a term only counts as "used" when it appears as a whole word, so "run" does not match
    inside "running" or "runway".
    """

    def __init__(self, terms: dict[str, str]) -> None:
        self.terms = terms
        # Longest terms first, so multi-word phrases are matched before their sub-words.
        self._patterns = [
            (src, tgt, re.compile(rf"(?<!\w){re.escape(src)}(?!\w)"))
            for src, tgt in sorted(terms.items(), key=lambda kv: len(kv[0]), reverse=True)
        ]

    @classmethod
    def load(cls, path: str | Path) -> Glossary:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"glossary file {path!r} must contain a JSON object of term mappings")
        return cls({str(k): str(v) for k, v in data.items()})

    def terms_in(self, text: str) -> list[tuple[str, str]]:
        """Return the (source_term, target_term) pairs that occur as whole words in `text`."""
        return [(src, tgt) for src, tgt, pattern in self._patterns if pattern.search(text)]

    def verify(self, segments: list[Segment]) -> tuple[list[Segment], dict[str, int]]:
        """Check that glossary terms found in each segment's source appear translated in its
        target. Segments missing an expected term are returned with `needs_review=True`.

        Returns the (possibly updated) segments and a report of {checked, honoured} term
        occurrences across the whole batch.
        """
        checked = 0
        honoured = 0
        out: list[Segment] = []
        for seg in segments:
            used = self.terms_in(seg.source)
            if not used or not seg.target:
                out.append(seg)
                continue
            missing = False
            for _src, tgt in used:
                checked += 1
                if re.search(rf"(?<!\w){re.escape(tgt)}(?!\w)", seg.target):
                    honoured += 1
                else:
                    missing = True
            if missing and not seg.needs_review:
                seg = Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    target=seg.target,
                    context_before=seg.context_before,
                    context_after=seg.context_after,
                    max_len=seg.max_len,
                    confidence=seg.confidence,
                    needs_review=True,
                    review_reason="sözlük terimi çeviride kullanılmamış",
                    from_memory=seg.from_memory,
                )
            out.append(seg)
        return out, {"checked": checked, "honoured": honoured}
