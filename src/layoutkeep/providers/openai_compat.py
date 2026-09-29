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

Bu modül yalnız sağlayıcıyı yönetir; mesajlar `chat_prompts`, yanıt okuma `reply_parser`,
sonuç temizliği `reply_cleanup` içinde. This module only orchestrates the provider; messages,
reply parsing and result cleanup live in those three modules.
"""

from __future__ import annotations

import json
import sys
import time

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
from layoutkeep.providers.chat_prompts import (
    build_messages,
    json_repair_messages,
    marker_repair_messages,
)
from layoutkeep.providers.reply_cleanup import apply_result
from layoutkeep.providers.reply_parser import markers_match, parse_reply, why_unreadable

#: Timeout used for requests that happen before `translate()` has computed anything adaptive
#: (`list_models()`, or `_chat()` if somehow called first) - only when the caller hasn't pinned
#: an explicit `timeout`.
DEFAULT_TIMEOUT = 60.0


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
        reply = self._chat(build_messages(segments, src_lang, tgt_lang, glossary))
        parsed = parse_reply(reply)
        if parsed is None:
            # One repair round: ask the model to turn its own broken reply into valid JSON.
            repaired = self._try_repair(reply)
            parsed = parse_reply(repaired) if repaired is not None else None
            if parsed is None:
                # Said out loud: two held-out paragraphs were never answered and nothing recorded
                # why, so the cause could only be guessed.
                print(
                    f"reply     unreadable for {len(segments)} segment(s): {why_unreadable(reply)}",
                    file=sys.stderr,
                )
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
            if block_id in by_seg and not markers_match(by_seg[block_id].source, target)
        ]
        repair_stats["repaired"] += len(mismatched)
        if mismatched:
            fixed = self._repair_markers([by_seg[i] for i in mismatched], by_id)
            for block_id in mismatched:
                candidate = (fixed or {}).get(block_id)
                if candidate is not None and markers_match(by_seg[block_id].source, candidate):
                    by_id[block_id] = candidate
                else:
                    repair_stats["still_mismatched"] += 1

        return [apply_result(seg, by_id.get(seg.block_id)) for seg in segments]

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
        """Ask the server once. A request that did not fit the context is a batch-size failure.

        Raising `BatchTooLargeError` is what lets the batching layer cut the batch down (and, for
        a single oversized segment, ask for its sentences one by one) instead of losing the chunk.
        """
        try:
            return self._transport.chat(self.model, messages, timeout=self._request_timeout)
        except RuntimeError as error:
            if _is_context_overflow(str(error)):
                raise BatchTooLargeError(
                    "REVIEW_CONTEXT_OVERFLOW"
                ) from error
            raise

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
    # Bozuk JSON için tek onarım turu / one repair round for a broken JSON reply
    try:
        return chat_fn(json_repair_messages(broken_reply))
    except (OSError, KeyError, json.JSONDecodeError):
        return None


def repair_marker_messages(
    chat_fn, segments: list[Segment], current_targets: dict[str, str],
) -> dict[str, str] | None:
    # Kaybolan işaretçiler için tek onarım turu / one repair round for lost markers
    try:
        reply = chat_fn(marker_repair_messages(segments, current_targets))
    except (OSError, KeyError):
        return None
    return parse_reply(reply)


#: What a server says when the request did not fit the model's context window. LM Studio answers
#: a request over the limit with HTTP 500 and "Context size has been exceeded" inside the body -
#: which the transport then reported as "Model ... bulunamadı veya yüklenmedi", sending the user to
#: look for a model that was loaded and answering. Measured on the first chunk of an 841-page
#: textbook that hit it: one segment too large for an 8192-token window.
_CONTEXT_MARKERS = (
    "context size",
    "context length",
    "maximum context",
    "context window",
    "too many tokens",
    "reduce the length",
)


def _is_context_overflow(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CONTEXT_MARKERS)
