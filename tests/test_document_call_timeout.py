"""A document-level call waits as long as a run's first batch, not the 60 s default.

WHY THIS EXISTS: the automatic glossary is asked before any batch is translated, so it ran under the
provider's starting timeout of 60 s while the first batch gets 240 s. On a slow local server the
forty-term answer took longer than a minute, the call timed out on all four bench sources, and every
run translated without the glossary it was configured for.
"""

from __future__ import annotations

from layoutkeep.providers.base import chat_callable


class _Provider:
    def __init__(self, timeout: float | None) -> None:
        self.timeout = timeout
        self._request_timeout = timeout if timeout is not None else 60.0
        self.first_batch_base_timeout = 240.0
        self.seen: list[float] = []

    def _chat(self, messages):
        self.seen.append(self._request_timeout)
        return "{}"


class _Wrapper:
    def __init__(self, inner) -> None:
        self.inner = inner


def test_a_document_call_gets_the_first_batch_allowance():
    provider = _Provider(timeout=None)

    chat_callable(_Wrapper(provider))([{"role": "user", "content": "x"}])

    assert provider.seen == [240.0]
    assert provider._request_timeout == 60.0, "the run's own timeout is restored afterwards"


def test_a_pinned_timeout_is_respected():
    provider = _Provider(timeout=30.0)

    chat_callable(provider)([{"role": "user", "content": "x"}])

    assert provider.seen == [30.0]


def test_a_provider_without_a_chat_call_still_has_none():
    assert chat_callable(object()) is None
