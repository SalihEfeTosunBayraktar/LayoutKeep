"""What each stretch of a document is about, asked of the model once per stretch.

WHY THIS EXISTS: a novel's opening, middle and end are about different things, so a single global
preamble cannot describe the whole book. Per page would be right in spirit and ruinous in cost - one
request per page on a 400-page book is hours. Stretches of about `batch_chars` characters keep the
narrative-local signal at a measured ~1.5% of a run's time.

Layout-blind (D2): reads the document's blocks, returns plain dictionaries keyed by block id. The
segment builder is the only consumer, and it looks the keywords up per block id rather than
recomputing anything.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

#: A model call: system prompt, user prompt, answer text. Kept as a parameter so this module can be
#: tested without a provider, and so the worker can pass whichever provider the run is using.
Ask = Callable[[str, str], str]

SYSTEM_PROMPT = "You name what a passage is about. Reply with only a JSON array."

#: Blocks shorter than this are noise for a topic map (a heading, a page number).
MIN_BLOCK_CHARS = 40


def _stretches(document, batch_chars: int) -> list[tuple[str, list[str]]]:
    """Group the document's text blocks into stretches of about `batch_chars` characters."""
    blocks = [
        ((block.source_text or block.text or "").strip(), block.id)
        for page in document.pages
        for block in page.blocks
    ]
    blocks = [(text, block_id) for text, block_id in blocks if len(text) >= MIN_BLOCK_CHARS]
    stretches: list[tuple[str, list[str]]] = []
    current: list[str] = []
    ids: list[str] = []
    size = 0
    for text, block_id in blocks:
        current.append(text)
        ids.append(block_id)
        size += len(text)
        if size >= batch_chars:
            stretches.append(("\n".join(current), ids))
            current, ids, size = [], [], 0
    if current:
        stretches.append(("\n".join(current), ids))
    return stretches


def _parse_keywords(reply: str, per_batch: int) -> list[str]:
    """Pull the keyword list out of a model answer, tolerating fences and prose around it."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.lstrip("json").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        words = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(words, list):
        return []
    return [str(word).strip() for word in words[:per_batch] if str(word).strip()]


def build_keyword_map(
    document,
    ask: Ask,
    *,
    batch_chars: int = 8000,
    per_batch: int = 8,
) -> list[dict]:
    """One entry per stretch: the block ids it covers and what the model says it is about.

    A stretch the model fails on is kept with an empty keyword list rather than dropped: the caller
    can report the gap instead of silently shipping a map with holes in it.
    """
    entries: list[dict] = []
    stretches = _stretches(document, batch_chars)
    for index, (text, block_ids) in enumerate(stretches):
        prompt = (
            f"Here is part {index + 1} of {len(stretches)} of a document.\n\n"
            f"{text[: batch_chars * 2]}\n\n"
            f"Reply with ONLY a JSON array of at most {per_batch} short keywords or key phrases "
            "naming what THIS part is about: the subjects, the people and the terms a translator "
            "must keep in mind here. No prose, no markdown fences. An empty array is better than "
            "invented words."
        )
        try:
            reply = ask(SYSTEM_PROMPT, prompt)
            words = _parse_keywords(reply, per_batch)
        except Exception as error:  # noqa: BLE001 - a failed stretch must not cost the run
            print(f"   [{index + 1}/{len(stretches)}] CALL FAILED {type(error).__name__}: {error}")
            words = []
        entries.append(
            {"index": index, "chars": len(text), "block_ids": block_ids, "keywords": words}
        )
    return entries


def write_keyword_map(entries: list[dict], path: str | Path) -> Path:
    """Write the map where the segment builder reads it and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def filled_entries(entries: list[dict]) -> tuple[int, int]:
    """How many stretches came back with keywords, and how many keywords there are in total."""
    return (
        sum(1 for entry in entries if entry.get("keywords")),
        sum(len(entry.get("keywords") or []) for entry in entries),
    )
