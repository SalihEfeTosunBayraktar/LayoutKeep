"""Tests for the DeepL provider.

DeepL cannot lose a segment or hand one back untranslated - it takes an array of strings and
returns an array of strings. What it can do is mangle the two things DocIR needs carried
through: inline style markers and protected values. Those are what these tests are about.
"""

from __future__ import annotations

import json
import urllib.error
import xml.etree.ElementTree as ET

import pytest

from layoutkeep.core.docir import Segment
from layoutkeep.core.protect import protect, restore
from layoutkeep.providers.deepl import (
    FREE_HOST,
    MAX_TEXTS_PER_REQUEST,
    PAID_HOST,
    DeepLProvider,
    from_deepl_markup,
    resolve_host,
    to_deepl_lang,
    to_deepl_markup,
)


class FakeDeepL:
    """Stands in for the service: records requests, echoes texts through a transform."""

    def __init__(self, transform=lambda t: f"TR({t})", short_by: int = 0) -> None:
        self.requests: list[dict] = []
        self.transform = transform
        self.short_by = short_by

    def __call__(self, request, timeout=None):  # urlopen signature
        payload = json.loads(request.data.decode("utf-8"))
        self.requests.append(payload)
        texts = [self.transform(t) for t in payload["text"]]
        if self.short_by:
            texts = texts[: len(texts) - self.short_by]
        body = json.dumps({"translations": [{"text": t} for t in texts]}).encode("utf-8")

        class _Response:
            def read(self_inner):
                return body

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Response()


def _provider(monkeypatch, fake: FakeDeepL) -> DeepLProvider:
    monkeypatch.setattr("layoutkeep.providers.deepl.urllib.request.urlopen", fake)
    return DeepLProvider("key:fx")


def _segments(*sources: str) -> list[Segment]:
    return [Segment(block_id=f"b{i}", source=s) for i, s in enumerate(sources)]


# -- host and language mapping ---------------------------------------------------------


def test_a_free_key_goes_to_the_free_host():
    """A free key sent to the paid host answers 403, which reads like a bad key."""
    assert resolve_host("abc:fx") == FREE_HOST
    assert resolve_host("abc") == PAID_HOST
    assert resolve_host("abc:fx", "https://proxy.example/") == "https://proxy.example"


@pytest.mark.parametrize(
    ("code", "expected"),
    [("tr", "TR"), ("TR", "TR"), ("de", "DE"), ("en", "EN-US"), ("pt", "PT-PT"), ("", "")],
)
def test_target_languages_use_the_variant_deepl_demands(code, expected):
    assert to_deepl_lang(code, target=True) == expected


def test_source_language_stays_plain():
    """DeepL rejects a regional variant as a source language."""
    assert to_deepl_lang("en-GB", target=False) == "EN"


# -- markup round trip -----------------------------------------------------------------


def test_style_markers_become_valid_xml_and_come_back():
    """`<0>` is not a legal XML name, so it travels as `<lk0>`."""
    source = "This is a <0>bold</0> word."

    wire = to_deepl_markup(source)

    assert "<lk0>" in wire and "</lk0>" in wire
    assert "<0>" not in wire
    assert from_deepl_markup(wire) == source


def test_protected_values_travel_inside_an_ignored_element():
    source_text = "Tighten the bolts to 150 Nm."
    protection = protect(source_text)

    wire = to_deepl_markup(protection.text)
    assert "<lkv>" in wire, "a protected value was not wrapped for ignore_tags"

    back = from_deepl_markup(wire)
    restored, missing = restore(back, protection)
    assert restored == source_text
    assert missing == 0


def test_literal_angle_brackets_cannot_become_markup():
    """A `<` in the document must not turn into a tag once tag_handling is on."""
    source = "Use a value < 5 & keep it."

    wire = to_deepl_markup(source)

    assert "&lt;" in wire and "&amp;" in wire
    assert from_deepl_markup(wire) == source


def test_control_characters_from_a_pdf_cannot_break_the_request():
    """Measured: page 2 of an arXiv paper carried a lone backspace (\\x08) in one segment's source.

    DeepL parses the text as XML and rejected the whole 40-segment request over that one byte -
    "Tag handling parsing failed ... not well-formed (invalid token)". XML-illegal control
    characters are dropped before anything else happens; tab, newline and carriage return are
    legal and stay.
    """
    source = "tok\x08en \x0c and \x1f here\ttab\nnewline"

    wire = to_deepl_markup(source)

    ET.fromstring(f"<r>{wire}</r>")  # noqa: S314 - our own generated string, not untrusted input
    assert "\x08" not in wire and "\x0c" not in wire and "\x1f" not in wire
    assert "\t" in wire and "\n" in wire
    assert from_deepl_markup(wire) == "token  and  here\ttab\nnewline"


def test_a_control_character_inside_a_protected_value_is_safe_too():
    """The protected element is written by us, so it is escaped by us as well."""
    protection = protect("Tighten the bolts to 1\x0850 Nm.")

    wire = to_deepl_markup(protection.text)

    ET.fromstring(f"<r>{wire}</r>")  # noqa: S314 - our own generated string, not untrusted input
    assert "\x08" not in wire


def test_markers_and_protected_values_together():
    protection = protect("Tighten the <0>4 bolts</0> to 63 Nm.")
    wire = to_deepl_markup(protection.text)
    assert "<lk0>" in wire and "<lkv>" in wire
    assert from_deepl_markup(wire) == protection.text


# -- the provider ----------------------------------------------------------------------


def test_translations_keep_their_segments(monkeypatch):
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)

    results = provider.translate(_segments("One.", "Two.", "Three."), "en", "tr")

    assert [r.block_id for r in results] == ["b0", "b1", "b2"]
    assert results[1].target == "TR(Two.)"
    assert [r.source for r in results] == ["One.", "Two.", "Three."]


def test_the_request_asks_for_tag_handling_and_ignores_our_value_element(monkeypatch):
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)

    provider.translate(_segments("Hello."), "en", "tr")

    sent = fake.requests[0]
    assert sent["tag_handling"] == "xml"
    assert sent["ignore_tags"] == ["lkv"]
    assert sent["target_lang"] == "TR"
    assert sent["source_lang"] == "EN"


def test_a_short_reply_flags_rather_than_shifting_every_translation(monkeypatch):
    """Positional matching is the contract; one missing reply must not move all the rest."""
    fake = FakeDeepL(short_by=1)
    provider = _provider(monkeypatch, fake)

    results = provider.translate(_segments("One.", "Two.", "Three."), "en", "tr")

    assert results[0].target == "TR(One.)"
    assert results[1].target == "TR(Two.)"
    assert results[2].target == ""
    assert results[2].needs_review
    assert "yanıtlamadı" in results[2].review_reason


def test_long_documents_are_split_into_several_requests(monkeypatch):
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)
    count = MAX_TEXTS_PER_REQUEST + 5

    results = provider.translate(_segments(*[f"Line {i}." for i in range(count)]), "en", "tr")

    assert len(results) == count
    assert len(fake.requests) == 2
    assert len(fake.requests[0]["text"]) == MAX_TEXTS_PER_REQUEST
    assert len(fake.requests[1]["text"]) == 5


def test_formality_is_only_sent_when_asked_for(monkeypatch):
    """DeepL errors on `formality` for languages that have no formal register."""
    fake = FakeDeepL()
    monkeypatch.setattr("layoutkeep.providers.deepl.urllib.request.urlopen", fake)

    DeepLProvider("k:fx").translate(_segments("Hi."), "en", "tr")
    assert "formality" not in fake.requests[0]

    DeepLProvider("k:fx", formality="more").translate(_segments("Hi."), "en", "tr")
    assert fake.requests[1]["formality"] == "more"


@pytest.mark.parametrize(
    ("code", "expected_words"),
    [(403, ["anahtar", "api-free"]), (456, ["kota"]), (413, ["büyük"])],
)
def test_http_errors_say_what_to_do(monkeypatch, code, expected_words):
    def raiser(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, code, "err", {}, None)

    monkeypatch.setattr("layoutkeep.providers.deepl.urllib.request.urlopen", raiser)

    with pytest.raises(RuntimeError) as excinfo:
        DeepLProvider("k:fx").translate(_segments("Hi."), "en", "tr")

    message = str(excinfo.value).lower()
    for word in expected_words:
        assert word.lower() in message


def test_a_missing_target_language_is_refused_before_any_request(monkeypatch):
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)

    with pytest.raises(ValueError):
        provider.translate(_segments("Hi."), "en", "")

    assert fake.requests == []


def test_progress_is_reported_the_way_every_caller_reads_it(monkeypatch):
    """The GUI always passes `on_progress`, and nothing in this file ever did.

    So the one line that builds a BatchProgress here was never executed by a test, and it
    built one with two of its six fields - which meant every DeepL translation in the desktop
    app died with a TypeError the moment its first batch came back. It only failed on the
    success path, which is why the error tests all passed.
    """
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)
    segments = _segments("One.", "Two.", "Three.")
    seen = []

    results = provider.translate(segments, "en", "tr", on_progress=seen.append)

    assert seen, "on_progress never called"
    last = seen[-1]
    assert last.segments_done == len(results) == 3
    assert last.segments_total == 3
    assert last.chars_done == sum(len(s.source) for s in segments)
    assert last.chars_total == last.chars_done
    assert last.elapsed_s >= 0.0
    assert last.batch_size > 0


def test_auto_source_language_is_omitted_rather_than_sent(monkeypatch):
    """"auto" is the setup screen's default source language, and DeepL has no such code.

    Sending it answers `Value for 'source_lang' not supported` (HTTP 400) and the job dies
    before a word is translated - which is what a real run did. DeepL detects the language
    when the field is absent.
    """
    fake = FakeDeepL()
    provider = _provider(monkeypatch, fake)

    provider.translate(_segments("One."), "auto", "tr")

    assert "source_lang" not in fake.requests[0]
    assert fake.requests[0]["target_lang"] == "TR"
