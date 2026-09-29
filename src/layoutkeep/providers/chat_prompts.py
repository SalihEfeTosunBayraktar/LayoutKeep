"""Chat messages sent to an OpenAI-compatible model: translate, fix JSON, fix markers.

Modele gönderilen sohbet mesajlarını kurar: çeviri isteği, JSON onarımı ve işaretçi onarımı.
Builds the chat messages for the model: the translation request, JSON repair and marker repair.
The wire contract (a JSON array of {id, text}) is fixed here; only the role line, a document
preamble and extra lines are user-tunable (see `build_messages`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.core.langs import english_name, script_note

#: Bozuk yanıtı geçerli JSON'a çevirme talimatı / instruction to turn a broken reply into JSON.
JSON_REPAIR_INSTRUCTION = (
    'The previous reply was not valid JSON. Return ONLY a valid JSON '
    'array of {"id": string, "text": string} objects, no prose, no '
    "markdown fences."
)


def json_repair_messages(broken_reply: str) -> list[dict[str, str]]:
    """Messages asking the model to rewrite its own broken reply as valid JSON.

    Modelden kendi bozuk yanıtını geçerli JSON olarak yeniden yazmasını ister.
    """
    return [
        {"role": "system", "content": JSON_REPAIR_INSTRUCTION},
        {"role": "user", "content": broken_reply},
    ]


def marker_repair_messages(
    segments: list[Segment], current_targets: dict[str, str]
) -> list[dict[str, str]]:
    items = [
        {
            "id": seg.block_id,
            "source": seg.source,
            "your_previous_translation": current_targets.get(seg.block_id, ""),
        }
        for seg in segments
    ]
    system_lines = [
        (
            "Your previous translation for these segments lost or misplaced the numbered "
            "markers like <0> and </0> that must stay in the output."
        ),
        (
            "Re-translate each segment's `source`, keeping the same meaning as your previous "
            "translation, but make sure every marker from `source` reappears exactly once in "
            "your output, wrapped around the translated equivalent of the words it wrapped in "
            "the source. Do not renumber markers and do not invent new ones."
        ),
        (
            'Reply with ONLY a JSON array of {"id": string, "text": string} objects, one per '
            "input segment, no prose, no markdown fences."
        ),
    ]
    return [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
    ]


def build_messages(
    segments: list[Segment],
    src_lang: str,
    tgt_lang: str,
    glossary: dict[str, str] | None,
) -> list[dict[str, str]]:
    # Wire format note for whoever picks up switching this (tracked separately, not done here -
    # see AdaptiveBatchSize, which lowers the urgency but doesn't remove the underlying problem):
    # this asks for one JSON array covering the whole batch and reparses it as a whole
    # (`parse_reply`). Measured behaviour (four local models 4B-14B, then gemma-4-e4b on a
    # correctly configured server) is that this is exactly what breaks as batch size grows - not
    # a timeout, but the array itself coming back incomplete or malformed (e.g. 3/6 entries at
    # size 6 for gemma-4-e4b). A format that let a partial reply still be parsed incrementally
    # (e.g. newline-delimited JSON, one object per line, parsed line by line as it streams)
    # would likely tolerate a larger batch before failing, and would fail partially instead of
    # all-or-nothing. Not changed here because AdaptiveBatchSize already recovers a batch that's
    # too large by shrinking and retrying, so the payoff of a wire format change is smaller now -
    # but it would still very likely raise the ceiling AdaptiveBatchSize discovers per model.
    items = [
        {
            "id": seg.block_id,
            "text": seg.source,
            "context_before": seg.context_before,
            "context_after": seg.context_after,
            "max_len": seg.max_len,
        }
        for seg in segments
    ]
    system_lines = [
        f"You are a professional translator from {english_name(src_lang)} to {english_name(tgt_lang)}.",
        "Input is a JSON array of segments, each with an id and text to translate.",
        (
            f"Write every translation entirely in {english_name(tgt_lang)}: its own spelling, its "
            "own grammar, its own script. Do not leave the source language's words in place and do "
            "not answer in a third language." + script_note(tgt_lang)
        ),
        (
            "context_before and context_after are given ONLY as context - never translate "
            "them and never include them in your output."
        ),
        # The page cuts blocks where the layout breaks, not where sentences end. Judged on four
        # documents, 4 of 13 critical errors were a model finishing a cut-off sentence from its
        # context, or dropping the half-sentence a block began with.
        (
            "A segment may start or end mid-sentence, because the page breaks it there. Translate "
            "exactly the words it contains, as a fragment if it is one: never complete it from "
            "the context, never drop its opening or closing words, never add or leave out content."
        ),
        (
            "When max_len is set for a segment, write its translation SHORT enough to stay "
            "within that many characters - a shorter statement of the same meaning. Do not "
            "pad, do not expand, maxLength is a hard limit measured in characters."
        ),
        (
            "Some text contains numbered markers like <0>...</0> or <1>...</1>. Reproduce "
            "every marker exactly in your translation - never renumber a marker, never add "
            "one that was not in the source, never drop one - but wrap each pair around the "
            "translated equivalent of the words it wrapped in the source, not around the "
            "same word position. Word order changes between languages, so a marker may move. "
            'Example: source "This is a <0>bold</0> word" translated to German becomes '
            '"Dies ist ein <0>fettes</0> Wort" - the marker follows "bold" to wherever its '
            "translation lands, it does not stay on the second word."
        ),
        (
            "Some text contains placeholder tokens: a digit wrapped in the characters U+E000 "
            "and U+E001. Each one stands for a measurement, a part number or a similar exact "
            "value that must not be translated. Copy every token through unchanged, keep each "
            "one exactly once, and move it to wherever its value belongs in the target "
            "sentence. Never translate, reword, renumber or expand a token."
        ),
        (
            'Reply with ONLY a JSON array of {"id": string, "text": string} objects, one '
            "per input segment, no prose, no markdown fences."
        ),
    ]
    # Only the terms this batch contains, as a requirement: all forty on one line let a small model
    # miss the one that mattered, and a term came out differently from page to page.
    text = " ".join(seg.source for seg in segments)
    present = {
        src: tgt for src, tgt in (glossary or {}).items()
        if re.search(rf"(?<!\w){re.escape(src)}(?!\w)", text, re.IGNORECASE)
    }
    if present:
        terms = "; ".join(f"{src} -> {tgt}" for src, tgt in present.items())
        system_lines.append(
            "These terms occur in the segments. Translate each one exactly as given (inflect it only "
            f"as the grammar requires), every time it occurs: {terms}"
        )

    # The wire protocol above is not negotiable: a reply that is not the JSON array, or that lost a
    # marker or a protected token, is a reply the pipeline cannot put back on the page. What a user
    # may change is the part that is instruction rather than contract - the role line and whatever
    # else they want said - so a document preamble and free-form extra lines are appended here, and
    # a file may replace the role line. Everything the parser depends on stays put.
    preamble = str(tunables.get("translation.document_preamble") or "").strip()
    if preamble:
        system_lines.append(f"About this document (context only, never translate it): {preamble}")
    extra = str(tunables.get("provider.system_prompt_extra") or "").strip()
    if extra:
        system_lines.append(extra)
    prompt_file = str(tunables.get("provider.system_prompt_file") or "").strip()
    if prompt_file:
        try:
            role = Path(prompt_file).read_text(encoding="utf-8").strip()
        except OSError:
            role = ""  # a missing file must not cost the run its instructions
        if role:
            system_lines[0] = role
    return [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
    ]
