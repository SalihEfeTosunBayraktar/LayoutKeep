"""Unit tests for FakeProvider - no network."""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.fake import FakeProvider


def _segments() -> list[Segment]:
    return [
        Segment(block_id="b1", source="Hello"),
        Segment(block_id="b2", source="World"),
        Segment(block_id="b3", source="Refused text"),
    ]


def test_normal_translation_matches_by_id():
    provider = FakeProvider(translations={"b1": "Bonjour", "b2": "Monde"})
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b1"].target == "Bonjour"
    assert by_id["b1"].needs_review is False
    assert by_id["b2"].target == "Monde"
    # segment without an explicit translation falls back to the deterministic default
    assert by_id["b3"].target == "[fr] Refused text"


def test_block_id_preserved_and_not_matched_by_position():
    segments = _segments()
    provider = FakeProvider(translations={"b3": "X", "b1": "Y", "b2": "Z"})
    result = provider.translate(segments, "en", "fr")

    # order of the result should not matter for correctness; match by id
    result_ids = {seg.block_id for seg in result}
    source_ids = {seg.block_id for seg in segments}
    assert result_ids == source_ids
    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b1"].target == "Y"
    assert by_id["b2"].target == "Z"
    assert by_id["b3"].target == "X"


def test_malformed_reply_marks_needs_review_without_copying_source():
    provider = FakeProvider(malformed_ids={"b2"})
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b2"].needs_review is True
    assert by_id["b2"].target == ""
    assert by_id["b2"].target != by_id["b2"].source  # never silently copy source to target


def test_refused_segment_marks_needs_review_without_copying_source():
    provider = FakeProvider(refuse_ids={"b3"})
    result = provider.translate(_segments(), "en", "fr")

    by_id = {seg.block_id: seg for seg in result}
    assert by_id["b3"].needs_review is True
    assert by_id["b3"].target == ""


def test_returns_one_segment_per_input_segment():
    segments = _segments()
    provider = FakeProvider()
    result = provider.translate(segments, "en", "fr")
    assert len(result) == len(segments)


def test_drop_marker_ids_strips_inline_style_markers_from_target():
    segments = [Segment(block_id="b1", source="a <0>bold</0> word")]
    provider = FakeProvider(
        translations={"b1": "un mot <0>gras</0>"}, drop_marker_ids={"b1"}
    )
    result = provider.translate(segments, "en", "fr")

    assert result[0].target == "un mot gras"
    assert "<0>" not in result[0].target
