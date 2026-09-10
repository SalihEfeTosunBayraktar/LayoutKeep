"""DeepL provider: a machine-translation service instead of an instruction-following model.

Every other provider here talks to a chat model and asks it to return a JSON array of
`{id, text}` objects. Measured against real models, that protocol is where the failures live:
30% of replies were not valid JSON at all, and only 20% were free of a segment handed back
untranslated (`docs/MEASUREMENTS.md`). DeepL cannot fail either way - it takes an array of
strings and returns an array of strings in the same order, and "leave it in English" is not
something it can do.

What it cannot do is follow instructions, so the two things DocIR needs carried through the
translation have to be expressed in terms DeepL already understands:

  * **Inline style markers.** DocIR wraps a bold or italic run as `<0>bold</0>`. DeepL moves
    XML tags to where their content lands in the target sentence, which is exactly the
    behaviour those markers need and the thing chat models get wrong most often (57% marker
    fidelity on the measured baseline). XML element names may not begin with a digit, so
    `<0>` is sent as `<lk0>` and renamed back on the way out.
  * **Protected values.** `core/protect.py` replaces torques, part numbers and form
    identifiers with PUA-delimited tokens before any provider sees them. Those are sent
    wrapped in an `<lkv>` element listed in `ignore_tags`, so DeepL leaves the contents alone
    rather than treating an unfamiliar private-use character as noise to drop.

Standard library only, like the rest of `providers/`.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request

from layoutkeep.core import tunables
from layoutkeep.core.docir import Segment
from layoutkeep.providers._http_compat import _retry_delay
from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.batching import BatchProgress, ProgressCallback

#: DeepL accepts up to 50 texts per request. Segments are short, so the character limit is the
#: binding one in practice; this keeps requests comfortably inside both.
MAX_TEXTS_PER_REQUEST = 40

#: Free API keys end in `:fx` and must go to a different host. Sending a free key to the paid
#: host answers 403, which reads like a bad key rather than the wrong address.
FREE_HOST = "https://api-free.deepl.com"
PAID_HOST = "https://api.deepl.com"

#: The languages DeepL translates, as LayoutKeep language codes. Our own list is wider, and
#: every code outside this set answers HTTP 400 ("Value for 'source_lang' not supported") - the
#: whole job failing on a choice the interface offered. The interface narrows the language
#: pickers to these while a DeepL profile is active rather than letting the run fail.
SUPPORTED_LANGUAGES = frozenset(
    {
        "ar", "cs", "da", "de", "el", "en", "es", "fi", "fr", "he", "hu", "id", "it", "ja",
        "ko", "nl", "no", "pl", "pt", "ro", "ru", "sv", "tr", "uk", "vi", "zh",
    }
)

#: DeepL names Norwegian by its written standard; the plain code is refused.
_LANG_ALIASES = {"NO": "NB"}

#: Targets DeepL will not accept bare: it wants a regional variant and rejects the plain code.
_TARGET_VARIANTS = {"EN": "EN-US", "PT": "PT-PT", "ZH": "ZH-HANS"}

_MARKER_RE = re.compile(r"<(/?)(\d+)>")
_LK_MARKER_RE = re.compile(r"<(/?)lk(\d+)>")
_PUA_RE = re.compile("(\\d+)")
_LKV_RE = re.compile(r"<lkv>\s*(\d+)\s*</lkv>")


def resolve_host(api_key: str, base_url: str | None = None) -> str:
    """Which DeepL host a key belongs to. An explicit base_url always wins."""
    if base_url:
        return base_url.rstrip("/")
    return FREE_HOST if api_key.strip().endswith(":fx") else PAID_HOST


def to_deepl_lang(code: str, *, target: bool) -> str:
    """Map a LayoutKeep language code onto DeepL's.

    DeepL wants upper case, and for a few targets insists on a regional variant - asking for
    plain `EN` is an error, not a default.
    """
    base = (code or "").strip().upper().replace("_", "-").split("-")[0]
    # The setup screen offers "auto" as a source language and it is the default. DeepL has no
    # such code - it detects the language when `source_lang` is left out entirely - so sending
    # it answers `Value for 'source_lang' not supported` and the whole job fails before a word
    # is translated. An empty string here means "do not send the field" to the caller, and as a
    # target it is refused outright, which is right: there is nothing to detect.
    if not base or base == "AUTO":
        return ""
    base = _LANG_ALIASES.get(base, base)
    if target:
        return _TARGET_VARIANTS.get(base, base)
    return base


def to_deepl_markup(text: str) -> str:
    """Turn DocIR's markers and protected tokens into XML DeepL will respect.

    Literal text is entity-escaped first so that a stray `<` or `&` in the document cannot
    turn into markup; our own elements are inserted afterwards and so survive intact.
    """
    pieces: list[str] = []
    cursor = 0
    for match in re.finditer(f"{_MARKER_RE.pattern}|{_PUA_RE.pattern}", text):
        pieces.append(html.escape(text[cursor : match.start()], quote=False))
        closing, number, protected = match.group(1), match.group(2), match.group(3)
        if protected is not None:
            pieces.append(f"<lkv>{protected}</lkv>")
        else:
            pieces.append(f"<{closing}lk{number}>")
        cursor = match.end()
    pieces.append(html.escape(text[cursor:], quote=False))
    return "".join(pieces)


def from_deepl_markup(text: str) -> str:
    """Undo `to_deepl_markup`, restoring DocIR's markers and protected tokens."""
    restored = _LKV_RE.sub(lambda m: f"{m.group(1)}", text)
    restored = _LK_MARKER_RE.sub(lambda m: f"<{m.group(1)}{m.group(2)}>", restored)
    return html.unescape(restored)


class DeepLProvider(TranslationProvider):
    """Translates through DeepL's `/v2/translate` endpoint.

    Ordering is the contract: DeepL returns translations in the order the texts were sent, so
    results are matched back positionally within a request. Segments are never reordered and
    the reply is checked to be the same length before anything is written back - a short reply
    leaves those segments flagged rather than silently shifting every translation by one.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = 60.0,
        formality: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.host = resolve_host(api_key, base_url)
        self.timeout = timeout
        #: DeepL rejects `formality` for languages that have no formal register, so it is only
        #: sent when the caller asked for one.
        self.formality = formality
        self.last_stats = {"requests": 0, "characters": 0}

    # -- transport ---------------------------------------------------------
    def _post(self, texts: list[str], source: str, target: str) -> list[str]:
        payload: dict[str, object] = {
            "text": texts,
            "target_lang": target,
            "tag_handling": "xml",
            # Our protected values must come back byte-identical; this is the whole reason a
            # machine-translation service can be trusted with a torque figure at all.
            "ignore_tags": ["lkv"],
        }
        if source:
            payload["source_lang"] = source
        if self.formality:
            payload["formality"] = self.formality

        request = urllib.request.Request(
            f"{self.host}/v2/translate",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "LayoutKeep",
            },
            method="POST",
        )

        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as err:
                last_error = err
                if err.code in (429, 529) and attempt < max_retries - 1:
                    time.sleep(_retry_delay(err, attempt))
                    continue
                raise RuntimeError(_explain_http_error(err)) from err
            except urllib.error.URLError as err:
                raise RuntimeError(f"DeepL'e ({self.host}) bağlanılamadı: {err.reason}") from err
        else:  # pragma: no cover - loop always breaks or raises
            raise RuntimeError(f"DeepL yanıt vermedi: {last_error}")

        translations = body.get("translations")
        if not isinstance(translations, list):
            # Not a type error in the caller's code: the server sent something unexpected,
            # which belongs in the same class as any other bad response from it.
            raise RuntimeError(  # noqa: TRY004
                f"DeepL beklenmeyen yanıt verdi: {str(body)[:200]}"
            )
        return [str(item.get("text", "")) for item in translations]

    def check_connection(self) -> str:
        """Ask DeepL who this key is, without translating anything.

        `/v2/usage` costs no characters, so a connection test never eats quota - and the reply
        says how much of it is left, which is the thing a user checks a DeepL key for.
        """
        request = urllib.request.Request(
            f"{self.host}/v2/usage",
            headers={
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "User-Agent": "LayoutKeep",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            raise RuntimeError(_explain_http_error(err)) from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"DeepL'e ({self.host}) bağlanılamadı: {err.reason}") from err

        used = body.get("character_count")
        limit = body.get("character_limit")
        if isinstance(used, int) and isinstance(limit, int):
            return f"DeepL bağlantısı çalışıyor - kota: {used:,} / {limit:,} karakter"
        return "DeepL bağlantısı çalışıyor"

    # -- provider ----------------------------------------------------------
    def translate(
        self,
        segments: list[Segment],
        src_lang: str,
        tgt_lang: str,
        glossary: dict[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        source = to_deepl_lang(src_lang, target=False)
        target = to_deepl_lang(tgt_lang, target=True)
        if not target:
            raise ValueError("DeepL için hedef dil gerekli.")

        results: list[Segment] = []
        stats = {"requests": 0, "characters": 0}
        total_chars = sum(len(seg.source) for seg in segments)
        run_started = time.monotonic()
        per_request = tunables.get("deepl.max_texts_per_request")
        for start in range(0, len(segments), per_request):
            chunk = segments[start : start + per_request]
            payload_texts = [to_deepl_markup(seg.source) for seg in chunk]
            stats["requests"] += 1
            stats["characters"] += sum(len(t) for t in payload_texts)

            replies = self._post(payload_texts, source, target)
            for index, seg in enumerate(chunk):
                out = Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    context_before=seg.context_before,
                    context_after=seg.context_after,
                    max_len=seg.max_len,
                    confidence=seg.confidence,
                    needs_review=seg.needs_review,
                    review_reason=seg.review_reason,
                )
                if index < len(replies):
                    out.target = from_deepl_markup(replies[index])
                else:
                    # A short reply must not shift every later translation onto the wrong
                    # segment. Leave it untranslated and say why.
                    out.needs_review = True
                    out.review_reason = "DeepL bu segmenti yanıtlamadı"
                results.append(out)

            if on_progress is not None:
                on_progress(
                    BatchProgress(
                        segments_done=len(results),
                        segments_total=len(segments),
                        chars_done=sum(len(s.source) for s in segments[: len(results)]),
                        chars_total=total_chars,
                        elapsed_s=time.monotonic() - run_started,
                        batch_size=len(chunk),
                    )
                )

        self.last_stats = stats
        return results


def _explain_http_error(err: urllib.error.HTTPError) -> str:
    # DeepL'in hata kodlarını ne yapılacağını söyleyen cümlelere çevirir / Actionable messages
    if err.code == 403:
        return (
            "DeepL anahtarı reddedildi (403). Anahtarın doğru olduğundan ve ücretsiz "
            "anahtarların (`:fx` ile biter) api-free.deepl.com adresine gittiğinden emin olun."
        )
    if err.code == 456:
        return "DeepL karakter kotası doldu (456). Bu ay için kota bitti."
    if err.code == 413:
        return "DeepL isteği çok büyük buldu (413). Daha küçük parti deneyin."
    body = err.read().decode("utf-8", errors="replace")[:200] if hasattr(err, "read") else ""
    return f"DeepL hatası (HTTP {err.code}): {body}"
