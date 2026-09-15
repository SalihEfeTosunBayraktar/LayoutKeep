"""Translation is a transformation, not a puzzle - so the model is asked not to reason.

Measured against gemma-4-e4b on LM Studio, translating one sentence:

    default                       487 completion tokens, 465 of them reasoning
    reasoning_effort="none"        15 completion tokens,   0 reasoning
    chat_template_kwargs
      {"enable_thinking": false}  426 completion tokens, 407 reasoning (no effect)

Thirty-two times the generated tokens, spent writing an essay about how to translate a
sentence before translating it. It was not only slow: the reasoning filled the context too, and
a 524-page run was failing batches with `{"code":500,"message":"Context size has been
exceeded."}` and retrying them smaller, over and over.

`reasoning_effort` is a standard OpenAI-compatible field, but not every server knows it, and a
server that does not may answer 400. That is the same status LM Studio returns for a model that
is not loaded, and this transport already turns a 400 into "model not found - load it in LM
Studio", which would be a confusing lie. So a 400 on a request that carried the field is retried
once without it, and only a second 400 is reported.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from layoutkeep.providers._http_compat import OpenAIHTTPTransport

_REPLY = {"choices": [{"message": {"content": "Etkinlestirme girisi."}}]}


class _Server:
    """Records the bodies it is posted, and answers with a scripted sequence."""

    def __init__(self, *, reject_reasoning: bool = False, reject_everything: bool = False) -> None:
        self.bodies: list[dict] = []
        self.reject_reasoning = reject_reasoning
        self.reject_everything = reject_everything

    def __call__(self, req, timeout):  # matches execute_http_post's signature
        body = json.loads(req.data.decode("utf-8"))
        self.bodies.append(body)
        rejected = self.reject_everything or (
            self.reject_reasoning and "reasoning_effort" in body
        )
        if rejected:
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", {},  # type: ignore[arg-type]
                _FakeBody(b'{"error":"unknown parameter: reasoning_effort"}'),
            )
        return _REPLY


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        """HTTPError closes the body it was handed; without this the GC complains."""


def _transport(server: _Server, **kwargs) -> OpenAIHTTPTransport:
    transport = OpenAIHTTPTransport("http://localhost:1234/v1", None, **kwargs)
    transport.execute_http_post = server  # type: ignore[method-assign]
    return transport


def test_reasoning_is_switched_off_by_default() -> None:
    server = _Server()
    assert _transport(server).chat("m", [{"role": "user", "content": "x"}], timeout=5)
    assert server.bodies[0]["reasoning_effort"] == "none"


def test_a_server_that_rejects_the_field_is_retried_without_it() -> None:
    server = _Server(reject_reasoning=True)
    result = _transport(server).chat("m", [{"role": "user", "content": "x"}], timeout=5)

    assert result == "Etkinlestirme girisi."
    assert len(server.bodies) == 2, "should have retried exactly once"
    assert "reasoning_effort" in server.bodies[0]
    assert "reasoning_effort" not in server.bodies[1]


def test_a_real_400_still_reports_the_model_problem() -> None:
    """Dropping the field must not swallow the case the 400 handler was written for."""
    server = _Server(reject_everything=True)
    with pytest.raises(RuntimeError, match="bulunamadı veya yüklenmedi"):
        _transport(server).chat("m", [{"role": "user", "content": "x"}], timeout=5)
    assert len(server.bodies) == 2


def test_it_can_be_turned_off() -> None:
    """A model that translates better when it reasons must still be allowed to."""
    server = _Server()
    transport = _transport(server, reasoning_effort=None)
    assert transport.chat("m", [{"role": "user", "content": "x"}], timeout=5)
    assert "reasoning_effort" not in server.bodies[0]
