"""HTTP transport for any server speaking the OpenAI /v1/chat/completions API.

Owns all urllib I/O and the retry / error-translation policy for `/v1/chat/completions`
and `/v1/models`. Kept separate from `OpenAICompatProvider` so that provider stays a
pure orchestration layer (batching, message construction, reply parsing/repair): the
network concerns live here, behind a small surface the provider composes.

Standard library only (urllib.request), no extra dependency.

Verified endpoint facts (see .claude/agents/lk-provider.md):
  - LM Studio default base_url: http://localhost:1234/v1, API key optional.
  - Ollama default base_url:    http://localhost:11434/v1, API key required but ignored.
  - Both expose GET /v1/models. Ollama's `owned_by` is always "library" and `created` is the
    last-modified time, not a real creation date - don't trust either for anything meaningful.
  - Ollama's OpenAI-compat layer breaks on `n`, `tool_choice`, `logit_bias`, `logprobs`, `user`.
    This transport never sends any of them.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from layoutkeep.core import tunables

#: Longest we will sit on a Retry-After before giving up on it. A free tier occasionally
#: answers with minutes, and a translation job should fail with a clear message rather than
#: appear frozen for that long.
_MAX_RETRY_AFTER_S = 60.0


def _retry_delay(err: Exception, attempt: int) -> float:
    """How long to wait before retrying a 429/503.

    Free API tiers rate-limit aggressively and say how long to wait in `Retry-After`. The
    fixed 2s/4s backoff ignored that, so all three attempts could be spent inside a window the
    server had already told us to sit out, and the job failed against a provider that was
    working fine. Falls back to the linear backoff when the header is absent or unparsable.
    """
    fallback = 2.0 * (attempt + 1)
    headers = getattr(err, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    if not raw:
        return fallback
    try:
        # The header is either delta-seconds or an HTTP date; only the former is worth honouring
        # here, since a date implies a wait long enough that failing loudly is kinder.
        seconds = float(str(raw).strip())
    except (TypeError, ValueError):
        return fallback
    if seconds <= 0:
        return fallback
    return min(seconds, tunables.get("http.max_retry_after_s"))


class OpenAIHTTPTransport:
    """All HTTP I/O for an OpenAI-compat server: headers, POST, chat retry, models list.

    Constructed with the parts of the request that are constant across calls (base URL,
    optional API key). Per-call arguments (timeout, model id, messages) are passed into
    `chat()` / `list_models()` so the same transport can be reused across batches with
    varying timeouts and never holds a mutable `self.timeout`.
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def headers(self) -> dict[str, str]:
        """Authorization + Content-Type. Sends a placeholder key when `api_key is None`
        because some clients (Ollama) require the header to be present even when its
        value is ignored.

        Adds OpenRouter attribution headers when targeting openrouter.ai - those let the
        request show up in the OpenRouter dashboard as LayoutKeep rather than anonymous.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or 'not-needed'}",
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://github.com/layoutkeep"
            headers["X-Title"] = "LayoutKeep"
        return headers

    def execute_http_post(self, req: urllib.request.Request, timeout: float) -> dict:
        """POST `req` and return the decoded JSON body. Raises whatever urllib raises -
        callers translate connection-level errors into RuntimeError with a usable message."""
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def parse_chat_response(self, payload: object) -> str:
        """Validate a /v1/chat/completions payload and extract `choices[0].message.content`.

        Raises RuntimeError for every malformed shape we have actually seen from local
        servers - error objects, missing/empty `choices`, missing `content`. Keeping these
        translations here (rather than inline in `chat()`) means `_parse_chat_response`
        stays independently testable.
        """
        if not isinstance(payload, dict):
            raise TypeError(f"Yapay zeka sunucusundan geçersiz yanıt tipi geldi: {type(payload)}")

        if "error" in payload:
            err = payload["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Yapay zeka model hatası: {msg}")

        choices = payload.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            msg = payload.get("message") or payload.get("detail") or str(payload)
            raise RuntimeError(f"Yapay zeka yanıtı 'choices' içermiyor. Sunucu mesajı: {msg}")

        message_obj = choices[0].get("message")
        if not message_obj or "content" not in message_obj:
            raise RuntimeError(f"Yapay zeka yanıtı içerik ('content') taşımıyor: {choices[0]}")

        return message_obj["content"]

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        timeout: float,
    ) -> str:
        """POST a /v1/chat/completions request and return the assistant content string.

        Retry policy (see _chat() in `OpenAICompatProvider` before this split):
          - HTTP 429/503: up to 3 attempts with linear backoff (2s, 4s).
          - HTTP 400/404: model not loaded / not found - one-shot RuntimeError telling the
            user to download the model in LM Studio, with the raw server body as a hint.
          - Other HTTPError: surface as RuntimeError with the raw body.
          - Transient RuntimeError ("overload", "rate limit", "503", "429", "temporarily"):
            same retry/backoff as 429/503.
          - URLError (connection refused, DNS failure, etc.): converted to RuntimeError
            naming the server URL - the caller's `try/except RuntimeError` catches it.
          - 3 attempts exhausted: RuntimeError naming the last underlying error.

        A `RuntimeError` raised after the last retry is what the batching layer translates
        into `needs_review` (or propagates, if it's the first batch).
        """
        body = {"model": model, "messages": messages, "temperature": 0.0}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=self.headers(),
            method="POST",
        )
        max_retries = 3
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                payload = self.execute_http_post(req, timeout)
                return self.parse_chat_response(payload)
            except urllib.error.HTTPError as err:
                last_err = err
                err_body = err.read().decode("utf-8", errors="replace")
                if err.code in (429, 503) and attempt < max_retries - 1:
                    time.sleep(_retry_delay(err, attempt))
                    continue
                if err.code in (400, 404):
                    # K3: model bulunamadi/yuklenmedi - ham JSON yerine ne yapilacagini soyle.
                    # LM Studio'da model yuklu degilse 400 doner; kullaniciya traceback degil,
                    # tek cumle gostermek gerekir (ayni sinif: "sunucu yanit vermedi").
                    raise RuntimeError(
                        f"Model '{model}' bulunamadı veya yüklenmedi (HTTP {err.code}).\n"
                        f"LM Studio'da modelin indirilip yüklendiğinden emin olun "
                        f"({self.base_url} adresinde). Sunucu yanıtı: {err_body[:200]}"
                    ) from err
                raise RuntimeError(f"Sunucu hatası (HTTP {err.code}): {err_body}") from err
            except RuntimeError as err:
                last_err = err
                err_str = str(err).lower()
                is_transient = any(
                    w in err_str for w in ("overload", "rate limit", "503", "429", "temporarily")
                )
                if is_transient and attempt < max_retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise
            except urllib.error.URLError as err:
                raise RuntimeError(f"Sunucuya ({self.base_url}) bağlanılamadı: {err.reason}") from err

        raise RuntimeError(f"Yapay zeka yanıt vermedi: {last_err}")

    def list_models(self, timeout: float) -> list[str]:
        """GET /v1/models - returns the model ids the server currently has loaded/available."""
        req = urllib.request.Request(f"{self.base_url}/models", headers=self.headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return [m["id"] for m in payload.get("data", [])]
