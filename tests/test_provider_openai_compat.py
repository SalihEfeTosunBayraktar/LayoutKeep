"""Unit tests for OpenAICompatProvider. No network: _chat is monkeypatched."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from layoutkeep.core.docir import Segment
from layoutkeep.providers.openai_compat import OpenAICompatProvider, _build_messages, _parse_reply


def _segments() -> list[Segment]:
    return [
        Segment(block_id="b1", source="Hello"),
        Segment(block_id="b2", source="World"),
    ]


def _multi_segment_provider(**kwargs) -> OpenAICompatProvider:
    """A provider configured to keep several segments in one request, for tests that exercise
    single-request parsing/repair logic rather than the (default one-segment-per-request)
    chunking - see `providers/batching.DEFAULT_MAX_SEGMENTS`."""
    return OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", max_batch_segments=10, **kwargs
    )


def test_translate_matches_result_by_id(monkeypatch):
    provider = _multi_segment_provider()

    def fake_chat(messages):
        return json.dumps([{"id": "b2", "text": "Monde"}, {"id": "b1", "text": "Bonjour"}])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b1"].target == "Bonjour"
    assert by_id["b2"].target == "Monde"
    assert all(not seg.needs_review for seg in result)


def test_malformed_reply_triggers_repair_then_marks_review_if_still_broken(monkeypatch):
    provider = _multi_segment_provider()
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        return "not json at all"

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(_segments(), "en", "fr")

    assert len(calls) == 2  # first attempt + one repair attempt
    assert all(seg.needs_review for seg in result)
    assert all(seg.target == "" for seg in result)
    # never silently copy source into target
    assert all(seg.target != seg.source for seg in result)


def test_repair_succeeds_on_second_attempt(monkeypatch):
    provider = _multi_segment_provider()
    responses = iter(["not json", json.dumps([{"id": "b1", "text": "A"}, {"id": "b2", "text": "B"}])])

    monkeypatch.setattr(provider, "_chat", lambda messages: next(responses))
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b1"].target == "A"
    assert by_id["b1"].needs_review is False


def test_model_refusing_one_segment_marks_only_that_one_for_review(monkeypatch):
    provider = _multi_segment_provider()

    def fake_chat(messages):
        # model only returns b1, silently drops b2
        return json.dumps([{"id": "b1", "text": "Bonjour"}])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b1"].needs_review is False
    assert by_id["b2"].needs_review is True
    assert by_id["b2"].target == ""


def test_reviewed_segment_carries_a_reason(monkeypatch):
    # K1: needs_review=True olan segment nedenini de tasir / review flag must say why
    provider = _multi_segment_provider()

    def fake_chat(messages):
        return json.dumps([{"id": "b1", "text": "Bonjour"}])  # b2 dropped

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b2"].needs_review is True
    assert by_id["b2"].review_reason, "review_reason bos kalmamali"
    assert by_id["b1"].review_reason == ""  # sorunsuz segment sebep tasimaz


def test_empty_segments_returns_empty_without_calling_chat(monkeypatch):
    provider = OpenAICompatProvider(base_url="http://localhost:1234/v1", model="test-model")
    monkeypatch.setattr(
        provider, "_chat", lambda messages: (_ for _ in ()).throw(AssertionError("should not be called"))
    )
    assert provider.translate([], "en", "fr") == []


def test_headers_send_placeholder_when_api_key_missing():
    provider = OpenAICompatProvider(base_url="http://localhost:11434/v1", model="llama3")
    headers = provider._headers()
    assert headers["Authorization"] == "Bearer not-needed"


def test_http_400_model_not_loaded_gives_actionable_message(monkeypatch):
    # K3: model bulunamadi/yuklenmedi -> ham JSON traceback degil, ne yapilacagini soyleyen
    # tek mesaj (UI/CLI bu RuntimeError'i kullaniciya gosterir).
    import io
    import urllib.error

    provider = _multi_segment_provider()

    def _boom(req, timeout=60.0):
        fp = io.BytesIO(b'{"error":"model not found"}')
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, fp)

    monkeypatch.setattr(provider._transport, "execute_http_post", _boom)

    with pytest.raises(RuntimeError) as excinfo:
        provider._chat([{"role": "user", "content": "hi"}])

    message = str(excinfo.value)
    assert "bulunamadı" in message or "yüklenmedi" in message
    assert "test-model" in message
    assert "LM Studio" in message
    assert "model not found" in message  # ham govde ipucu olarak ekli, ama tek cumle icinde


def test_headers_use_real_api_key_when_provided():
    provider = OpenAICompatProvider(base_url="http://api.example.com/v1", model="gpt", api_key="sk-xyz")
    headers = provider._headers()
    assert headers["Authorization"] == "Bearer sk-xyz"


def test_build_messages_never_sends_unsupported_params():
    messages = _build_messages(_segments(), "en", "fr", glossary=None)
    payload = json.dumps(messages)
    for forbidden in ("tool_choice", "logit_bias", "logprobs", '"n":', "\"user\":"):
        assert forbidden not in payload


def test_build_messages_marks_context_as_not_to_translate():
    segments = [Segment(block_id="b1", source="Hi", context_before="prev", context_after="next")]
    messages = _build_messages(segments, "en", "fr", glossary=None)
    system_text = messages[0]["content"]
    assert "never translate" in system_text.lower()


def test_build_messages_includes_glossary_terms():
    messages = _build_messages(_segments(), "en", "fr", glossary={"widget": "gadget"})
    system_text = messages[0]["content"]
    assert "widget -> gadget" in system_text


def test_parse_reply_rejects_non_list_json():
    assert _parse_reply(json.dumps({"id": "b1", "text": "x"})) is None


def test_parse_reply_rejects_items_missing_fields():
    assert _parse_reply(json.dumps([{"id": "b1"}])) is None


def test_parse_reply_accepts_valid_array():
    parsed = _parse_reply(json.dumps([{"id": "b1", "text": "Bonjour"}]))
    assert parsed == {"b1": "Bonjour"}


def test_build_messages_instructs_marker_preservation():
    messages = _build_messages(_segments(), "en", "fr", glossary=None)
    system_text = messages[0]["content"]
    assert "<0>" in system_text
    assert "renumber" in system_text.lower()


def test_marker_roundtrip_survives_when_model_reply_is_correct(monkeypatch):
    """The prompt+parse path must not disturb a reply that already carries markers correctly."""
    provider = OpenAICompatProvider(base_url="http://localhost:1234/v1", model="test-model")
    segments = [Segment(block_id="b1", source="This is a <0>bold</0> word.")]

    def fake_chat(messages):
        return json.dumps([{"id": "b1", "text": "Dies ist ein <0>fettes</0> Wort."}])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "de")

    assert result[0].target == "Dies ist ein <0>fettes</0> Wort."
    assert result[0].needs_review is False
    assert provider.last_marker_repair_stats == {"repaired": 0, "still_mismatched": 0}


def test_marker_mismatch_triggers_one_repair_round_and_succeeds(monkeypatch):
    provider = OpenAICompatProvider(base_url="http://localhost:1234/v1", model="test-model")
    segments = [Segment(block_id="b1", source="This is a <0>bold</0> word.")]
    calls = []
    responses = iter(
        [
            # first reply drops the marker entirely
            json.dumps([{"id": "b1", "text": "Dies ist ein fettes Wort."}]),
            # repair round brings it back
            json.dumps([{"id": "b1", "text": "Dies ist ein <0>fettes</0> Wort."}]),
        ]
    )

    def fake_chat(messages):
        calls.append(messages)
        return next(responses)

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "de")

    assert len(calls) == 2
    assert result[0].target == "Dies ist ein <0>fettes</0> Wort."
    assert provider.last_marker_repair_stats == {"repaired": 1, "still_mismatched": 0}


def test_translate_splits_large_input_into_several_requests(monkeypatch):
    """A batch_chars small enough to force each segment into its own request must still
    translate everything and match results by id, not by call order."""
    provider = OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", batch_chars=1
    )
    segments = [Segment(block_id=f"b{i}", source="Hello") for i in range(3)]
    calls = []

    def fake_chat(messages):
        payload = json.loads(messages[1]["content"])
        calls.append([item["id"] for item in payload])
        return json.dumps([{"id": item["id"], "text": f"T-{item['id']}"} for item in payload])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "fr")

    assert calls == [["b0"], ["b1"], ["b2"]]
    by_id = {seg.block_id: seg.target for seg in result}
    assert by_id == {"b0": "T-b0", "b1": "T-b1", "b2": "T-b2"}


def test_translate_one_failed_batch_does_not_lose_earlier_successes(monkeypatch):
    provider = OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", batch_chars=1
    )
    segments = [Segment(block_id="b0", source="Hello"), Segment(block_id="b1", source="World")]

    def fake_chat(messages):
        payload = json.loads(messages[1]["content"])
        if payload[0]["id"] == "b1":
            raise TimeoutError("did not answer")
        return json.dumps([{"id": "b0", "text": "Bonjour"}])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b0"].target == "Bonjour"
    assert by_id["b0"].needs_review is False
    assert by_id["b1"].target == ""
    assert by_id["b1"].needs_review is True


def test_translate_first_batch_failure_propagates(monkeypatch):
    """A dead server should fail the whole call loudly and immediately, not finish silently
    with every segment needs_review - matching what cli.py and the GUI worker already handle."""
    provider = OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", batch_chars=1
    )
    segments = [Segment(block_id="b0", source="Hello"), Segment(block_id="b1", source="World")]

    def fake_chat(messages):
        raise TimeoutError("did not answer")

    monkeypatch.setattr(provider, "_chat", fake_chat)
    with pytest.raises(TimeoutError):
        provider.translate(segments, "en", "fr")


def test_translate_reports_progress_via_on_progress(monkeypatch):
    provider = OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", batch_chars=1
    )
    segments = [Segment(block_id="b0", source="Hello"), Segment(block_id="b1", source="World")]

    def fake_chat(messages):
        payload = json.loads(messages[1]["content"])
        return json.dumps([{"id": item["id"], "text": "x"} for item in payload])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    events = []
    provider.translate(segments, "en", "fr", on_progress=events.append)

    assert len(events) == 2
    assert events[0].segments_done == 1
    assert events[1].segments_done == 2
    assert events[1].segments_total == 2


def test_translate_adapts_timeout_from_measured_throughput(monkeypatch):
    """After the first batch, later batches should use the measured chars/sec rather than the
    conservative default guess, so a fast local model gets a shorter timeout, not always 240s+."""
    provider = OpenAICompatProvider(
        base_url="http://localhost:1234/v1", model="test-model", batch_chars=1
    )
    segments = [Segment(block_id="b0", source="Hello"), Segment(block_id="b1", source="World")]
    seen_timeouts = []

    def fake_chat(messages):
        seen_timeouts.append(provider._request_timeout)
        payload = json.loads(messages[1]["content"])
        return json.dumps([{"id": item["id"], "text": "x"} for item in payload])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    provider.translate(segments, "en", "fr")

    assert len(seen_timeouts) == 2
    # First batch gets the large cold-load allowance; second batch, informed by real elapsed
    # time from the first (near-zero here), must not carry the same 240s+ base forward.
    assert seen_timeouts[0] > seen_timeouts[1]


def test_translate_default_adaptive_grows_then_shrinks_and_recovers_on_short_reply(monkeypatch):
    """End-to-end version of the batching-layer adaptive tests: a provider left at its default
    `max_batch_segments` (ADAPTIVE) must grow the batch size on repeated success, treat a reply
    that comes back short as a size problem rather than individual refusals, and recover those
    segments by retrying smaller instead of leaving them needs_review."""
    provider = OpenAICompatProvider(base_url="http://localhost:1234/v1", model="test-model")
    segments = [Segment(block_id=f"b{i}", source="Hello") for i in range(6)]
    request_sizes: list[int] = []

    def fake_chat(messages):
        payload = json.loads(messages[1]["content"])
        request_sizes.append(len(payload))
        if len(payload) >= 3:
            # simulate the model losing entries as the batch grows: only the first item comes
            # back, never all of them.
            return json.dumps([{"id": payload[0]["id"], "text": "x"}])
        return json.dumps([{"id": item["id"], "text": "x"} for item in payload])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "fr")

    assert max(request_sizes) >= 3  # it did grow enough to hit the short-reply size
    assert all(not seg.needs_review for seg in result)
    assert all(seg.target == "x" for seg in result)


def test_marker_mismatch_detected_and_left_as_is_when_repair_fails(monkeypatch):
    """A reply that drops markers must never be silently accepted or reverted to source."""
    provider = OpenAICompatProvider(base_url="http://localhost:1234/v1", model="test-model")
    segments = [Segment(block_id="b1", source="This is a <0>bold</0> word.")]

    def fake_chat(messages):
        # both the first attempt and the repair round lose the marker
        return json.dumps([{"id": "b1", "text": "Dies ist ein fettes Wort."}])

    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.translate(segments, "en", "de")

    assert result[0].target == "Dies ist ein fettes Wort."  # left as-is, not source, not blanked
    assert provider.last_marker_repair_stats == {"repaired": 1, "still_mismatched": 1}


# -- explicit timeout override -------------------------------------------------------------


def _stalling_server() -> tuple[socket.socket, int, list[socket.socket]]:
    """A raw TCP server that accepts a connection and then never answers - stands in for a
    model server that is up but still loading (or just hung). The accepted connection is kept
    open, not closed, so the client sees a stall rather than a connection reset."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted: list[socket.socket] = []

    def _accept_and_stall() -> None:
        try:
            conn, _ = srv.accept()
            accepted.append(conn)
        except OSError:
            pass  # server closed while waiting - fine, test is already done

    threading.Thread(target=_accept_and_stall, daemon=True).start()
    return srv, port, accepted


def test_explicit_timeout_wins_over_the_computed_cold_load_base():
    """`timeout=` at construction must hold verbatim - not be overwritten by the adaptive
    per-batch computation, which defaults to a 240s cold-load base far longer than the 2s given
    here. Against real code with the old bug (translate() always recomputing `self.timeout` from
    `batch_timeout()`), this call blocks for the better part of 240s; here it must return in
    roughly the 2s the caller actually asked for."""
    srv, port, accepted = _stalling_server()
    try:
        provider = OpenAICompatProvider(
            base_url=f"http://127.0.0.1:{port}/v1", model="test-model", timeout=2.0
        )
        segments = [Segment(block_id="b1", source="Hello")]

        started = time.monotonic()
        with pytest.raises((TimeoutError, OSError)):
            provider.translate(segments, "en", "fr")
        elapsed = time.monotonic() - started

        assert elapsed < 15.0  # nowhere near the 240s cold-load base; generous margin for CI
    finally:
        for conn in accepted:
            conn.close()
        srv.close()


def test_parse_chat_response_handles_error_payload():
    # Sunucudan error objesi geldiğinde anlamlı hata fırlatıldığını doğrular
    provider = OpenAICompatProvider(base_url="http://localhost:11434/v1", model="test-model")
    with pytest.raises(RuntimeError, match="Yapay zeka model hatası: model 'foo' not found"):
        provider._parse_chat_response({"error": {"message": "model 'foo' not found"}})


def test_parse_chat_response_handles_missing_choices():
    # Choices alanı olmadığında veya boş olduğunda anlamlı hata fırlatıldığını doğrular
    provider = OpenAICompatProvider(base_url="http://localhost:11434/v1", model="test-model")
    with pytest.raises(RuntimeError, match="Yapay zeka yanıtı 'choices' içermiyor"):
        provider._parse_chat_response({"detail": "service unavailable"})

