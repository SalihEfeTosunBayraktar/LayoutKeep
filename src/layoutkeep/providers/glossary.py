"""Terminology dictionary: injected into the translation prompt and verified afterwards.

File format: JSON, a flat {source_term: target_term} object. Chosen over TSV because the
glossary is exactly the dict[str, str] shape `TranslationProvider.translate` already takes
for its `glossary` parameter (see base.py / openai_compat.py) - JSON round-trips that shape
with no parsing ambiguity (TSV would need escaping rules for terms containing tabs/newlines,
which glossary entries occasionally do for phrasal terms).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from layoutkeep.core.docir import Segment


def _target_pattern(term: str) -> re.Pattern[str]:
    """How the target term is found in a translation: at a word start, in any case, inflected.

    A whole-word, exact-case match flagged correct translations in every language that inflects:
    Turkish writes 'tamponun' for 'tampon', capitalises it at a sentence start, and softens a final
    consonant before a suffix ('ışık' -> 'ışığın'). So the term may carry a suffix, and a term of four
    letters or more may have its last letter changed when at least two more letters follow. The word
    start stays strict, so the term is never found inside another word.
    """
    escaped = re.escape(term)
    if len(term) >= 4:
        escaped = rf"(?:{escaped}|{re.escape(term[:-1])}\w\w)"
    return re.compile(rf"(?<!\w){escaped}", re.IGNORECASE)


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
        """Read a glossary from JSON, or from a two-column CSV/TSV file.

        CSV as well as JSON because a glossary usually starts life as a spreadsheet: translators
        and reviewers already keep term lists in one, and asking them to convert it by hand is a
        reason not to use the feature. The format is decided by the first non-empty character - a
        `{` means JSON, anything else is read as delimited text.
        """
        source = Path(path)
        text = source.read_text(encoding="utf-8-sig")
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            data = json.loads(text)
            if not isinstance(data, dict):
                raise TypeError(
                    f"glossary file {path!r} must contain a JSON object of term mappings"
                )
            return cls({str(k): str(v) for k, v in data.items()})
        return cls(cls._read_delimited(text))

    @staticmethod
    def _read_delimited(text: str) -> dict[str, str]:
        """Two columns per row, tab or comma or semicolon separated, header optional."""
        import csv
        import io

        sample = " ".join(line for line in text.splitlines() if line.strip())[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",	;")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
        pairs: dict[str, str] = {}
        for index, row in enumerate(rows):
            cells = [cell.strip() for cell in row]
            if len(cells) < 2 or not cells[0]:
                continue
            if index == 0 and cells[0].casefold() in {"source", "kaynak", "quellbegriff"}:
                continue  # a header row, not a term
            pairs[cells[0]] = cells[1]
        return pairs

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
                if _target_pattern(tgt).search(seg.target):
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
                    review_reason="REVIEW_GLOSSARY_MISS",
                    from_memory=seg.from_memory,
                )
            out.append(seg)
        return out, {"checked": checked, "honoured": honoured}


def load_terms(path: str | Path | None) -> dict[str, str] | None:
    """The term list in `path`, or None when no file is configured.

    One reader for both front-ends: the command line and the application have to agree on what the
    run's glossary is, or their translation memories end up keyed differently for the same job. An
    unreadable file raises - what a caller does about that is its own decision (the window reports
    it and translates without a glossary).
    """
    if not path:
        return None
    return Glossary.load(path).terms or None


def glossary_fingerprint(terms: dict[str, str]) -> str:
    """Short hash of a term list, folded into a translation-memory key.

    WHY THIS EXISTS: the memory is keyed by (source, languages, model). A glossary changes what the
    model is asked for, so a translation produced under a different term list must not be served
    back as an answer to this one - the case the memory's own warning describes. Both front-ends
    fold in this same hash, so the two keys agree on when a stored row still answers the question.
    """
    payload = chr(0).join(f"{k}={v}" for k, v in sorted(terms.items())).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]
