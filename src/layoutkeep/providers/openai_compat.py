"""Adapter for any server speaking the OpenAI /v1/chat/completions API.

Covers LM Studio, Ollama, llama.cpp server, vLLM, OpenRouter, Groq, OpenAI itself - anything
with that endpoint shape. Standard library only (urllib.request), no extra dependency.

Verified endpoint facts (see .claude/agents/lk-provider.md):
  - LM Studio default base_url: http://localhost:1234/v1, API key optional.
  - Ollama default base_url:    http://localhost:11434/v1, API key required but ignored.
  - Both expose GET /v1/models. Ollama's `owned_by` is always "library" and `created` is the
    last-modified time, not a real creation date - don't trust either for anything meaningful.
  - Ollama's OpenAI-compat layer breaks on `n`, `tool_choice`, `logit_bias`, `logprobs`, `user`.
    This adapter never sends any of them.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter

from layoutkeep.core.docir import Segment
from layoutkeep.providers._http_compat import OpenAIHTTPTransport
from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.batching import (
    ADAPTIVE,
    DEFAULT_BATCH_CHARS,
    FIRST_BATCH_BASE_TIMEOUT_S,
    BatchTooLargeError,
    ProgressCallback,
    batch_timeout,
    run_batches,
)

#: Timeout used for requests that happen before `translate()` has computed anything adaptive
#: (`list_models()`, or `_chat()` if somehow called first) - only when the caller hasn't pinned
#: an explicit `timeout`.
DEFAULT_TIMEOUT = 60.0

#: Matches the numbered inline-style markers DocIR wraps around a run, e.g. `<0>` / `</0>`.
#: This layer never learns what a marker means (D2) - it only has to carry the token through.
_MARKER_RE = re.compile(r"<(/?)(\d+)>")


class OpenAICompatProvider(TranslationProvider):
    """Translates segments via a /v1/chat/completions endpoint.

    `api_key` is optional - most local servers (LM Studio, Ollama) don't check it. When omitted,
    a placeholder is still sent in the Authorization header for clients that require the header
    to be present even if its value is ignored.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float | None = None,
        batch_chars: int = DEFAULT_BATCH_CHARS,
        max_batch_segments: int | str | None = ADAPTIVE,
        first_batch_base_timeout: float = FIRST_BATCH_BASE_TIMEOUT_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        #: HTTP taşıma katmanı: tüm urllib I/O, retry ve hata çevirisi burada (tek sorumluluk).
        self._transport = OpenAIHTTPTransport(self.base_url, self.api_key)
        #: Explicit per-request timeout override. `None` (the default) means `translate()`
        #: computes an adaptive timeout for every batch (see `providers.batching.batch_timeout`)
        #: - the right default, since nobody can predict a cold local model's load time up
        #: front. A number pins every request to exactly that many seconds and disables the
        #: recompute entirely: this is the seam a caller uses to say "no more than N seconds"
        #: and have it hold - including a caller that sets `.timeout` between calls instead of
        #: passing it to the constructor (e.g. the GUI worker, which recomputes its own
        #: per-outer-batch value and expects it to be used verbatim, not silently replaced).
        self.timeout = timeout
        #: Base allowance `translate()` gives the first batch of a run, in `batch_timeout()`'s
        #: `first_batch_base` (see there) - defaults to the module constant, which assumes the
        #: model isn't loaded yet. A caller who knows the server already has it warm can pass a
        #: lower value instead of waiting out 240s of headroom it doesn't need. Only takes
        #: effect while `timeout` is `None` (adaptive); a pinned `timeout` ignores it entirely.
        self.first_batch_base_timeout = first_batch_base_timeout
        #: Timeout actually applied to the *next* request - what `_chat()` and `list_models()`
        #: read. Starts at `timeout` if one was given, else `DEFAULT_TIMEOUT`; `translate()`
        #: updates it before every batch (see `translate()`).
        self._request_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        #: Character budget per request (see providers/batching.py). translate() splits its
        #: input into several requests of roughly this size instead of sending everything in
        #: one call, which times out or never returns once a job reaches book length.
        self.batch_chars = batch_chars
        #: How many segments go in one request. Defaults to `ADAPTIVE` (see
        #: `batching.AdaptiveBatchSize`): starts at one segment per request and grows while
        #: replies keep coming back complete and parseable, shrinking - permanently, as a
        #: ceiling - the moment one does not. Reliable batch size varies roughly fivefold
        #: between models (measured: 1 for a 9B model, 5 for gemma-4-e4b on a correctly
        #: configured server), so no fixed constant is right for every model. Pass an int to
        #: pin a fixed size instead - e.g. the batch benchmark tool wants reproducible timings,
        #: not a moving target.
        self.max_batch_segments = max_batch_segments
        #: Set by the last translate() call: how many segments needed a marker-repair round
        #: and how many still had mismatched markers afterwards. The CLI reports this.
        self.last_marker_repair_stats = {"repaired": 0, "still_mismatched": 0}

    # -- public API --------------------------------------------------------

    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        """Translate `segments`, split into several requests sized by `batch_chars` and
        `self.max_batch_segments`.

        Once at least one batch has succeeded, a later batch that raises (timeout, connection
        error) does not lose the batches that already succeeded - it comes back with
        `needs_review=True` instead of aborting the whole call. But if the very first batch
        raises, nothing has been salvaged yet, so the exception (`TimeoutError`, `OSError`)
        propagates instead of being swallowed - a dead or unreachable server still fails loudly
        and immediately, matching what `cli.py` and the GUI worker already handle (see
        `providers/batching.run_batches`).

        The per-request timeout is adapted per batch by default: the first request keeps a
        large allowance for a cold model load, later ones use the throughput measured from the
        first successful request. Setting `self.timeout` to a number instead of `None` pins
        every batch to that timeout verbatim and turns this adaptation off.

        `self.max_batch_segments == ADAPTIVE` (the default) additionally lets the batch size
        itself adapt: it grows while replies come back complete, and a batch that comes back
        malformed or short (`BatchTooLargeError`) is retried at a smaller size instead of being
        given up on - see `providers/batching.AdaptiveBatchSize`.
        """
        repair_stats = {"repaired": 0, "still_mismatched": 0}
        rate_state: dict[str, float | None] = {"chars_per_second": None}
        first_batch = True
        adaptive = self.max_batch_segments == ADAPTIVE

        def translate_one_batch(batch: list[Segment]) -> list[Segment]:
            nonlocal first_batch
            chars = sum(
                len(s.source) + len(s.context_before) + len(s.context_after) for s in batch
            )
            if self.timeout is not None:
                # Explicit override wins: use it verbatim, no recompute.
                self._request_timeout = self.timeout
            else:
                self._request_timeout = batch_timeout(
                    chars,
                    is_first=first_batch,
                    chars_per_second=rate_state["chars_per_second"],
                    first_batch_base=self.first_batch_base_timeout,
                )
            started = time.monotonic()
            result = self._translate_batch(
                batch, src_lang, tgt_lang, glossary, repair_stats, adaptive=adaptive
            )
            elapsed = time.monotonic() - started
            if rate_state["chars_per_second"] is None and chars and elapsed > 0:
                rate_state["chars_per_second"] = chars / elapsed
            first_batch = False
            return result

        results = run_batches(
            segments,
            self.batch_chars,
            translate_one_batch,
            on_progress,
            max_segments=self.max_batch_segments,
        )
        self.last_marker_repair_stats = repair_stats
        return results

    def _translate_batch(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None,
        repair_stats: dict[str, int],
        *,
        adaptive: bool,
    ) -> list[Segment]:
        """Translate one already-sized batch in a single request (plus repair rounds).

        `adaptive` (true only when `self.max_batch_segments is ADAPTIVE`, see `translate()`):
        when a batch of more than one segment comes back with any segment missing from the
        reply - malformed JSON, or valid JSON with fewer entries than segments sent - this
        raises `BatchTooLargeError` instead of resolving the gaps to `needs_review` here,
        so `run_batches`' adaptive sizing can treat it as a size signal, shrink, and retry the
        same segments rather than spend them. A pinned (non-adaptive) provider, or a batch that
        is already down to one segment, keeps the old behaviour: gaps are resolved to
        `needs_review` right here, never raised.
        """
        reply = self._chat(_build_messages(segments, src_lang, tgt_lang, glossary))
        parsed = _parse_reply(reply)
        if parsed is None:
            # One repair round: ask the model to turn its own broken reply into valid JSON.
            repaired = self._try_repair(reply)
            parsed = _parse_reply(repaired) if repaired is not None else None
        by_id = parsed or {}

        if adaptive and len(segments) > 1:
            missing = [seg.block_id for seg in segments if seg.block_id not in by_id]
            if missing:
                raise BatchTooLargeError(
                    f"{len(missing)}/{len(segments)} segments missing from reply"
                )

        by_seg = {seg.block_id: seg for seg in segments}
        mismatched = [
            block_id
            for block_id, target in by_id.items()
            if block_id in by_seg and not _markers_match(by_seg[block_id].source, target)
        ]
        repair_stats["repaired"] += len(mismatched)
        if mismatched:
            fixed = self._repair_markers([by_seg[i] for i in mismatched], by_id)
            for block_id in mismatched:
                candidate = (fixed or {}).get(block_id)
                if candidate is not None and _markers_match(by_seg[block_id].source, candidate):
                    by_id[block_id] = candidate
                else:
                    repair_stats["still_mismatched"] += 1

        return [_apply_result(seg, by_id.get(seg.block_id)) for seg in segments]

    def list_models(self) -> list[str]:
        """GET /v1/models, returns the model ids the server currently has loaded/available."""
        return self._transport.list_models(timeout=self._request_timeout)

    # -- internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return self._transport.headers()

    def _parse_chat_response(self, payload: object) -> str:
        # Sunucu yanıtını doğrular ve içerik metnini çıkarır / Validates response payload
        return self._transport.parse_chat_response(payload)

    def _execute_http_post(self, req) -> dict:
        # HTTP isteğini gönderir ve JSON yanıtını döner / Executes HTTP POST request
        return self._transport.execute_http_post(req, timeout=self._request_timeout)

    def _chat(self, messages: list[dict[str, str]]) -> str:
        return self._transport.chat(self.model, messages, timeout=self._request_timeout)

    def _try_repair(self, broken_reply: str) -> str | None:
        return try_repair_reply(self._chat, broken_reply)

    def _repair_markers(
        self, segments: list[Segment], current_targets: dict[str, str]
    ) -> dict[str, str] | None:
        """One targeted round asking the model to fix marker placement for specific segments.

        Only sent for segments whose reply lost, renumbered or duplicated a marker. Segments
        that still mismatch afterwards are left untouched by the caller - core flags them via
        `needs_review` when it can't parse the markers back into spans.
        """
        return repair_marker_messages(self._chat, segments, current_targets)


def try_repair_reply(
    chat_fn, broken_reply: str,
) -> str | None:
    try:
        return chat_fn(
            [
                {
                    "role": "system",
                    "content": (
                        'The previous reply was not valid JSON. Return ONLY a valid JSON '
                        'array of {"id": string, "text": string} objects, no prose, no '
                        "markdown fences."
                    ),
                },
                {"role": "user", "content": broken_reply},
            ]
        )
    except (OSError, KeyError, json.JSONDecodeError):
        return None


def repair_marker_messages(
    chat_fn, segments: list[Segment], current_targets: dict[str, str],
) -> dict[str, str] | None:
    try:
        reply = chat_fn(_marker_repair_messages(segments, current_targets))
    except (OSError, KeyError):
        return None
    return _parse_reply(reply)


def _markers_match(source: str, target: str) -> bool:
    """True when `target` carries exactly the same multiset of markers as `source`.

    Word order changes across languages, so this checks the marker set, not its position.
    """
    return Counter(_MARKER_RE.findall(source)) == Counter(_MARKER_RE.findall(target))


def _marker_repair_messages(
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


def _apply_result(seg: Segment, target: str | None) -> Segment:
    """Build the outbound Segment for one input segment.

    `target is None` means the model never returned this id (refused, dropped it, or the
    reply stayed unparsable after the repair attempt) - marked for review, never filled in
    from the source text.
    """
    return Segment(
        block_id=seg.block_id,
        source=seg.source,
        target=target or "",
        context_before=seg.context_before,
        context_after=seg.context_after,
        max_len=seg.max_len,
        confidence=seg.confidence,
        needs_review=target is None,
        # K1: model bu id'yi dondurmediyse sebep yazilmali / review must say why
        review_reason=(
            "sağlayıcı bu segmenti yanıtlamadı / provider did not return this segment"
            if target is None
            else ""
        ),
        from_memory=False,
    )


def _build_messages(
    segments: list[Segment],
    src_lang: str,
    tgt_lang: str,
    glossary: dict[str, str] | None,
) -> list[dict[str, str]]:
    # Wire format note for whoever picks up switching this (tracked separately, not done here -
    # see AdaptiveBatchSize, which lowers the urgency but doesn't remove the underlying problem):
    # this asks for one JSON array covering the whole batch and reparses it as a whole
    # (`_parse_reply`). Measured behaviour (four local models 4B-14B, then gemma-4-e4b on a
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
        f"You are a professional translator from {src_lang} to {tgt_lang}.",
        "Input is a JSON array of segments, each with an id and text to translate.",
        (
            "context_before and context_after are given ONLY as context - never translate "
            "them and never include them in your output."
        ),
        (
            "When max_len is set for a segment, try to keep its translation within that "
            "many characters."
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
    if glossary:
        terms = "; ".join(f"{src} -> {tgt}" for src, tgt in glossary.items())
        system_lines.append(f"Use this glossary where the term appears: {terms}")
    return [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
    ]


def _parse_reply(reply: str) -> dict[str, str] | None:
    """Parse a model reply into {id: translated_text}. Returns None if it isn't the expected
    JSON array of {id, text} objects - the caller treats that as a malformed reply."""
    try:
        data = json.loads(reply)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            return None
        result[str(item["id"])] = str(item["text"])
    return result
