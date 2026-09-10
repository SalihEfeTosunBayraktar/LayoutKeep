"""Tests for the decorator that makes literal protection actually take effect.

`core/protect.py` was written, tested and then left unwired, so every value it knows how to
protect was still being handed to a translation model. These tests are about the wiring: that
data-only segments never become requests, that literals survive a model which rewrites the words
around them, and that a lost literal is reported rather than quietly dropped.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.base import TranslationProvider
from layoutkeep.providers.protected import ProtectedProvider


class RecordingProvider(TranslationProvider):
    """Records what it was asked to translate and answers with a caller-supplied transform."""

    def __init__(self, transform=lambda text: f"TR:{text}") -> None:
        self.seen: list[str] = []
        self.calls = 0
        self.transform = transform

    def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
        self.calls += 1
        self.seen.extend(s.source for s in segments)
        out = []
        for s in segments:
            seg = Segment(block_id=s.block_id, source=s.source)
            seg.target = self.transform(s.source)
            out.append(seg)
        return out


def _seg(block_id: str, source: str) -> Segment:
    return Segment(block_id=block_id, source=source)


def test_a_value_survives_a_model_that_rewrites_everything_around_it() -> None:
    inner = RecordingProvider(lambda text: text.replace("Tighten the bolts to", "Civatalari sikin:"))
    provider = ProtectedProvider(inner)

    (result,) = provider.translate([_seg("b1", "Tighten the bolts to 150 Nm.")], "en", "tr")

    assert "150 Nm" in result.target
    assert not result.needs_review


def test_the_model_never_sees_the_value() -> None:
    """The entire defence: a model cannot paraphrase what was never in its prompt."""
    inner = RecordingProvider()
    provider = ProtectedProvider(inner)

    provider.translate([_seg("b1", "Tighten the bolts (3) to 24.5 Nm.")], "en", "tr")

    sent = "".join(inner.seen)
    assert "24.5 Nm" not in sent
    assert "(3)" not in sent


def test_a_data_only_segment_is_never_sent() -> None:
    """A US tax form produced 29 of these. Each one was a request spent on a number."""
    inner = RecordingProvider()
    provider = ProtectedProvider(inner)

    segments = [_seg("b1", "19,999"), _seg("b2", "42"), _seg("b3", "Enter your total income")]
    results = provider.translate(segments, "en", "tr")

    assert inner.seen == ["Enter your total income"]
    assert [r.target for r in results[:2]] == ["19,999", "42"]
    assert provider.last_stats["skipped"] == 2


def test_a_model_that_loses_a_token_is_flagged_not_trusted() -> None:
    inner = RecordingProvider(lambda text: "Civatalari sikin.")  # drops the token entirely
    provider = ProtectedProvider(inner)

    (result,) = provider.translate([_seg("b1", "Tighten the bolts to 150 Nm.")], "en", "tr")

    assert result.needs_review
    assert provider.last_stats["lost"] == 1
    assert "150 Nm" not in result.target


def test_segments_come_back_in_order_with_their_real_source() -> None:
    """Callers match by block_id, but the source they see must be the untokenised original."""
    inner = RecordingProvider()
    provider = ProtectedProvider(inner)

    segments = [_seg("b1", "Torque to 63 Nm."), _seg("b2", "1545"), _seg("b3", "Plain prose.")]
    results = provider.translate(segments, "en", "tr")

    assert [r.block_id for r in results] == ["b1", "b2", "b3"]
    assert [r.source for r in results] == [s.source for s in segments]


def test_prose_without_values_is_passed_straight_through() -> None:
    inner = RecordingProvider()
    provider = ProtectedProvider(inner)

    provider.translate([_seg("b1", "Pull the knotter backward.")], "en", "tr")

    assert inner.seen == ["Pull the knotter backward."]
    assert provider.last_stats["protected"] == 0


def test_works_with_providers_that_predate_on_progress() -> None:
    """FakeProvider and CachedProvider do not accept `on_progress`, though the base class
    declares it. The stub above does accept it, which hid a TypeError that broke every real
    CLI run the moment protection was wired in. This stub is shaped like the real ones.
    """

    class OldStyleProvider(TranslationProvider):
        def translate(self, segments, src_lang, tgt_lang, glossary=None):
            out = []
            for s in segments:
                seg = Segment(block_id=s.block_id, source=s.source)
                seg.target = f"TR:{s.source}"
                out.append(seg)
            return out

    provider = ProtectedProvider(OldStyleProvider())
    (result,) = provider.translate([_seg("b1", "Torque to 63 Nm.")], "en", "tr")

    assert "63 Nm" in result.target


def test_a_reader_flag_survives_the_round_trip() -> None:
    """A segment the reader already flagged - mirrored text, a shaky OCR line - is rebuilt into
    a fresh Segment for the request. Returning that one unchanged drops the reader's verdict,
    and the CLI then reports needs_review=0 for a document it had itself flagged.
    """
    provider = ProtectedProvider(RecordingProvider())
    seg = _seg("b1", "Mirrored Label on a sign")
    seg.needs_review = True
    seg.review_reason = "metin aynalanmış"
    seg.confidence = 0.4

    (result,) = provider.translate([seg], "en", "tr")

    assert result.needs_review
    assert result.review_reason == "metin aynalanmış"
    assert result.confidence == 0.4
