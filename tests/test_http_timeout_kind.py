"""A timeout is a timeout, whichever step of the request it hit.

Zaman aşımı, isteğin hangi adımında olursa olsun zaman aşımıdır.

urllib raises a bare TimeoutError when the reply is slow, but wraps one that hits while connecting
or sending in URLError - and the transport reported that as "could not connect to the server". On
macOS CI the stalling-server test hit exactly that path, and a user would have been sent to check a
server that was up and merely slow. A refused connection is still "could not connect".
"""

from __future__ import annotations

import urllib.error

import pytest

from layoutkeep.providers._http_compat import OpenAIHTTPTransport


def _transport(error: Exception) -> OpenAIHTTPTransport:
    def post(_req, _timeout):
        raise error

    transport = OpenAIHTTPTransport("http://localhost:1234/v1", None)
    transport.execute_http_post = post  # type: ignore[method-assign]
    return transport


def _chat(transport: OpenAIHTTPTransport) -> None:
    transport.chat("m", [{"role": "user", "content": "hello"}], timeout=1)


def test_a_timeout_while_sending_is_reported_as_a_timeout() -> None:
    with pytest.raises(TimeoutError):
        _chat(_transport(urllib.error.URLError(TimeoutError("timed out"))))


def test_a_refused_connection_is_still_could_not_connect() -> None:
    with pytest.raises(RuntimeError, match="bağlanılamadı"):
        _chat(_transport(urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))))
