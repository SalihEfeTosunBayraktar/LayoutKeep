"""The document's own terms, rendered once, so every occurrence of them is translated alike.

WHY THIS EXISTS (docs/DECISIONS.md D-007): the topic half of the document-preamble idea hands the
model keywords in the SOURCE language, which cannot make a term's translation consistent - it still
picks a rendering per occurrence. What can is the glossary, which goes into every request and is
checked in the output; `core/terms.suggest_from_document` already finds the terms a document
repeats, and until now somebody had to translate them by hand. This module makes that one request.

Layout-blind (D2): reads blocks, returns a plain {source_term: target_term} dictionary - exactly
the shape `TranslationProvider.translate` takes and `Glossary` verifies. The ask callable is a
parameter, the arrangement `core/keywords.py` uses, so the parsing and every failure path are
testable without a provider.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from layoutkeep.core.langs import english_name

#: A model call: system prompt, user prompt, answer text. The same shape core/keywords.py declares.
Ask = Callable[[str, str], str]

SYSTEM_PROMPT = (
    "You give the settled translation of a document's terms. Reply with only a JSON object."
)

#: How much of the document the model is shown. The terms are the question; the excerpt is there
#: so a term of art can be told from a word that merely repeats, and so a proper name is
#: recognisable as one. This is the opening page of most documents, next to nothing beside the
#: translation itself.
CONTEXT_CHARS = 1500


def _excerpt(document, limit: int = CONTEXT_CHARS) -> str:
    """The document's first `limit` characters of translatable block text, in reading order."""
    parts: list[str] = []
    size = 0
    for _page, block in document.iter_blocks():
        text = (block.text or "").strip()
        if not text or not getattr(block, "translatable", True):
            continue
        parts.append(text)
        size += len(text)
        if size >= limit:
            break
    return "\n".join(parts)[:limit]


def _parse_glossary(reply: str) -> dict[str, str]:
    """Pull a {term: translation} object out of a model answer, tolerating fences and prose.

    Anything that is not an object of strings is not a glossary: a reply the parser cannot read
    becomes an empty list rather than a guess, the same rule `core/keywords._parse_keywords` keeps.
    """
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(term).strip(): value.strip()
        for term, value in data.items()
        if isinstance(value, str) and str(term).strip() and value.strip()
    }


def _prompt(document, candidates: list[str], source_lang: str, target_lang: str) -> str:
    source_name, target_name = english_name(source_lang), english_name(target_lang)
    listed = "\n".join(f"- {phrase}" for phrase in candidates)
    return (
        f"Here is the opening of a document written in {source_name}.\n\n"
        f"{_excerpt(document)}\n\n"
        f"These words and phrases recur throughout the rest of it:\n{listed}\n\n"
        f"Give each one its settled {target_name} rendering, as a JSON object mapping the term "
        f"to its {target_name} translation. Reply with ONLY that JSON object: no prose, no "
        "markdown fences. Keep a term unchanged when it should not be translated at all - a "
        "proper name, a code, a unit symbol. Omit a term you are not sure about: an omitted term "
        "is better than a guessed one."
    )


def build_doc_glossary(
    document,
    ask: Ask,
    *,
    source_lang: str,
    target_lang: str,
    limit: int = 40,
    exclude: set[str] | None = None,
) -> dict[str, str]:
    """Ask the model once for the target-language rendering of the terms a document repeats.

    ONE request for the whole document: a term recurs everywhere it recurs, so asking per page
    would buy nothing and cost a request per page - D-007 measured the per-page variant at about
    +160% of a run, where this is one call in total.

    A call that fails, or a reply nobody can read, returns an empty glossary: a missing term
    policy must never cost the run, and the caller still has the user's own file.
    """
    from layoutkeep.core.terms import suggest_from_document

    candidates = suggest_from_document(document, limit=limit, exclude=exclude)
    if not candidates:
        return {}
    # Keyed by the candidate's own spelling: `Glossary` matches a source term case-sensitively, so
    # a key the model re-cased would never be found in the document it belongs to.
    known = {candidate.phrase.casefold(): candidate.phrase for candidate in candidates}
    try:
        reply = ask(
            SYSTEM_PROMPT,
            _prompt(document, [candidate.phrase for candidate in candidates], source_lang, target_lang),
        )
    except Exception as error:  # noqa: BLE001 - a failed glossary must not cost the run
        print(f"   automatic glossary CALL FAILED {type(error).__name__}: {error}")
        return {}

    glossary: dict[str, str] = {}
    for term, target in _parse_glossary(reply).items():
        spelled = known.get(term.casefold())
        if spelled is not None:
            glossary[spelled] = target
    return glossary


def merge_glossaries(automatic: dict[str, str], user: dict[str, str] | None) -> dict[str, str]:
    """The automatic terms with the user's own on top: what the user decided is never overruled.

    The comparison is case-insensitive so one term cannot land in the merged list twice - two keys
    for the same words would fight each other inside every request.
    """
    decided = {term.casefold() for term in (user or {})}
    merged = {term: value for term, value in automatic.items() if term.casefold() not in decided}
    merged.update(user or {})
    return merged


def write_glossary(terms: dict[str, str], path: str | Path) -> Path:
    """Write the list beside the output and return the path: it is meant to be read by a person."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(terms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
