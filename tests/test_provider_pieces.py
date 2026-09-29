"""A paragraph the model hands back is asked for in pieces, and put back together.

The retry ladder resends a segment the model would not translate - in a small batch, then alone a
few times - and one paragraph survived every held-out document (IRS Publication 505, the 1895
mushroom book, the Sherlock Holmes EPUB, seven blocks on arXiv 2609.19145). The ladder changes the
request's company and its context, never its size; these tests hold the last resort that changes
the size, and the rules that keep reassembling honest: the source's own separators, no half
translation, and every piece accepted on its own before the whole is.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Segment
from layoutkeep.providers.retry import retry_untranslated
from layoutkeep.providers.split import pieces, reassemble

_PARAGRAPH = (
    "The quick brown fox jumps over the lazy dog. "
    "A second sentence follows it here. "
    "And a third one closes the paragraph."
)


def _reverse(source: str) -> str:
    """A stand-in translation sharing no words with its source (which would read as a copy)."""
    return "TR:" + source[::-1]


class _EchoesLongReplies:
    """Translates what it is asked for only when the request is one sentence.

    This is the measured behaviour, not a convenience: a Time Machine dialogue paragraph echoed in
    the main pass and in the batch retry, and translated 24 times out of 24 when sent alone.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, segments, **_kwargs):
        self.calls.append([s.source for s in segments])
        out = []
        for seg in segments:
            one_sentence = len(re.findall(r"[.!?]", seg.source)) <= 1
            out.append(
                Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    target=_reverse(seg.source) if one_sentence else seg.source,
                )
            )
        return out


class _FailsOnePiece:
    """Translates every piece but one, which comes back as its own source."""

    def translate(self, segments, **_kwargs):
        out = []
        for seg in segments:
            echo = "second sentence" in seg.source.casefold()
            out.append(
                Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    target=seg.source if echo else _reverse(seg.source),
                )
            )
        return out


def test_a_cut_keeps_the_sources_own_separators() -> None:
    source = "First sentence here. Second one here.\nThird one here."
    cut = pieces(source)
    assert [piece.text for piece in cut] == [
        "First sentence here.",
        "Second one here.",
        "Third one here.",
    ]
    # The whitespace is what is cut and put back; the sentence's own full stop stays in the piece,
    # so a reply is asked for a whole sentence rather than a fragment of one.
    assert [piece.following for piece in cut] == [" ", "\n", ""]
    assert (
        reassemble([_reverse(piece.text) for piece in cut], cut)
        == "TR:.ereh ecnetnes tsriF TR:.ereh eno dnoceS\nTR:.ereh eno drihT"
    )


def test_text_that_is_already_one_unit_is_not_cut() -> None:
    assert pieces("An encoder is a digital circuit.") == []
    assert pieces("") == []
    assert pieces("   \n  ") == []


def test_a_cut_whose_pieces_are_too_short_to_translate_is_refused() -> None:
    """A contents entry's numbers: cutting it buys a request per number and translates nothing."""
    assert pieces("5.2.1 Basic Components .... 27") == []


def test_a_text_that_cuts_into_too_many_pieces_is_not_cut() -> None:
    assert pieces("One here. " * 13) == []
    assert pieces("One here. " * 3)


def test_a_paragraph_the_model_echoes_is_translated_in_pieces() -> None:
    segment = Segment(block_id="b1", source=_PARAGRAPH)
    provider = _EchoesLongReplies()

    assert retry_untranslated(provider, [segment]) == 1

    assert segment.target.startswith("TR:")
    # Three pieces, each asked for on its own, after the whole paragraph failed, and put back in
    # the source's own whitespace.
    shortest = min(len(call[0]) for call in provider.calls)
    assert shortest < 60, "a single sentence should have been asked for on its own"
    cut = pieces(_PARAGRAPH)
    assert len(cut) == 3
    assert segment.target == reassemble([_reverse(piece.text) for piece in cut], cut)


def test_one_piece_that_fails_leaves_the_whole_paragraph_as_it_was() -> None:
    """A half-translated paragraph is worse than an untranslated one: it no longer reads as a
    loss, and the review queue cannot say what is missing."""
    segment = Segment(block_id="b1", source=_PARAGRAPH)
    assert retry_untranslated(_FailsOnePiece(), [segment]) == 0
    assert segment.target == ""


def test_pieces_that_each_come_back_as_their_own_source_are_not_assembled() -> None:
    class _EchoesEverything:
        def translate(self, segments, **_kwargs):
            return [
                Segment(block_id=s.block_id, source=s.source, target=s.source) for s in segments
            ]

    segment = Segment(block_id="b1", source=_PARAGRAPH)
    assert retry_untranslated(_EchoesEverything(), [segment]) == 0
    assert segment.target == ""


def test_cutting_can_be_turned_off() -> None:
    from layoutkeep.core import tunables

    segment = Segment(block_id="b1", source=_PARAGRAPH)
    tunables.set_value("translation.piecewise_max_pieces", 0)
    try:
        assert retry_untranslated(_EchoesLongReplies(), [segment]) == 0
        assert segment.target == ""
    finally:
        tunables.reset("translation.piecewise_max_pieces")
