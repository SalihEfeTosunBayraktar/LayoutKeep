"""Every request has a ceiling on how much the model may generate.

Campaign run 1, NIST SP 800-12: 38 minutes and not one page came back. The server log's last
completion was at 00:09:58; after that it kept generating and never finished - a reply that does
not stop, with nothing to stop it, holds its slot until it fills a 56,000-token context. Eight
such requests and the whole server is taken. A translation's length is bounded by what it
translates, so the ceiling is derived from the request, and a reply cut there comes back
malformed - which the provider already handles (split, retry, flag).
"""

from __future__ import annotations

import json

from layoutkeep.providers._http_compat import OpenAIHTTPTransport

_REPLY = {"choices": [{"message": {"content": "ok"}}]}


class _Server:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def __call__(self, req, timeout):
        self.bodies.append(json.loads(req.data.decode("utf-8")))
        return _REPLY


def _chat(user_content: str) -> dict:
    server = _Server()
    transport = OpenAIHTTPTransport("http://localhost:1234/v1", None)
    transport.execute_http_post = server  # type: ignore[method-assign]
    transport.chat(
        "m",
        [{"role": "system", "content": "You are a translator." * 50}, {"role": "user", "content": user_content}],
        timeout=5,
    )
    return server.bodies[0]


def test_a_request_carries_a_generation_ceiling() -> None:
    body = _chat('[{"id": "a", "text": "' + "word " * 200 + '"}]')
    assert isinstance(body.get("max_tokens"), int) and body["max_tokens"] > 0


def test_the_ceiling_scales_with_what_is_being_translated() -> None:
    short = _chat('[{"id": "a", "text": "Chip select"}]')["max_tokens"]
    long = _chat('[{"id": "a", "text": "' + "word " * 2000 + '"}]')["max_tokens"]
    assert long > short
    # Room for a translation that runs much longer than its source, as Turkish does.
    assert long >= len("word " * 2000) // 3


def test_the_ceiling_leaves_room_for_a_long_turkish_reply() -> None:
    """Campaign, Electricity in Agriculture: 13 replies were cut at the first ceiling (one output
    token per two characters sent) - a 1,213-token request stopped at 915 - and a 2,247-character
    paragraph never came back at all. Turkish takes more tokens than the English it translates."""
    text = "x" * 2247
    body = _chat('[{"id": "a", "text": "' + text + '"}]')
    assert body["max_tokens"] >= len(text)
