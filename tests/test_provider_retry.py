"""Segments that came back empty get one more attempt, on their own.

`run_batches` already retries a batch that *raises* - `BatchTooLargeError` shrinks the batch and
tries the same segments again. It cannot see the failure that actually cost text on
`computer-systems-Architecture.pdf`: the request succeeded, the reply came back, and some
segments in it simply had no translation attached. Nothing raised, so nothing was retried, and
those blocks kept their source text (see providers/passthrough.flag_untranslated).

Measured there: 17 of 210 segments, and with them a quarter of the prose on the page. Since a
lost segment is nearly always a reply the parser could not line up rather than text the model
refuses, asking again - in a much smaller batch, because there are only a handful left -
recovers most of them.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Segment
from layoutkeep.providers.retry import retry_untranslated


class _Recorder:
    """A provider that translates whatever it is handed, and remembers what that was."""

    def __init__(self, *, fails: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fails = fails or set()

    def translate(self, segments, **_kwargs):
        self.calls.append([s.block_id for s in segments])
        out = []
        for seg in segments:
            target = "" if seg.block_id in self.fails else _fake_translation(seg.source)
            out.append(
                Segment(
                    block_id=seg.block_id,
                    source=seg.source,
                    target=target,
                    context_before=seg.context_before,
                    context_after=seg.context_after,
                )
            )
        return out


def _fake_translation(source: str) -> str:
    """A stand-in translation that shares no words with its source. Prefixing the source ("TR:"
    + source) would itself be an untranslated copy, and the retry now rightly rejects those."""
    return "TR:" + source[::-1]


def _good(source: str) -> str:
    return "G" * len(source) + " " + " ".join(re.findall(r"\d+", source))


def _segment(block_id: str, source: str, target: str = "") -> Segment:
    return Segment(block_id=block_id, source=source, target=target)


_PROSE = "An encoder is a digital circuit that performs the inverse operation of a decoder."


def test_empty_segments_are_retried_and_filled() -> None:
    segments = [
        _segment("b1", _PROSE, target="TR:done"),
        _segment("b2", _PROSE),
        _segment("b3", _PROSE),
    ]
    provider = _Recorder()

    recovered = retry_untranslated(provider, segments)

    assert recovered == 2
    assert provider.calls == [["b2", "b3"]], "only the empty ones should be resent"
    assert segments[0].target == "TR:done", "an already-translated segment must not be touched"
    assert segments[1].target == _fake_translation(_PROSE)
    assert segments[2].target == _fake_translation(_PROSE)


def test_nothing_to_retry_makes_no_request() -> None:
    segments = [_segment("b1", _PROSE, target="TR:done")]
    provider = _Recorder()
    assert retry_untranslated(provider, segments) == 0
    assert provider.calls == []


def test_data_only_segments_are_left_alone() -> None:
    """Protection answers these without a request by design; resending them would waste the
    retry and invite a model to 'improve' a number."""
    segments = [_segment("b1", "10000000111")]
    provider = _Recorder()
    assert retry_untranslated(provider, segments) == 0
    assert provider.calls == []


def test_a_still_empty_reply_is_not_retried_again() -> None:
    """One extra attempt, not a loop - a segment the model will not translate must not hold the
    job open."""
    segments = [_segment("b1", _PROSE)]
    provider = _Recorder(fails={"b1"})
    assert retry_untranslated(provider, segments) == 0
    assert provider.calls == [["b1"]]
    assert segments[0].target == ""


def test_a_failing_retry_does_not_lose_what_already_worked() -> None:
    """The retry is a bonus pass over a document that is otherwise finished. If the server dies
    between the main run and the retry, the translations already in hand must survive."""

    class _Dead:
        def translate(self, segments, **_kwargs):
            raise OSError("connection reset")

    segments = [_segment("b1", _PROSE, target="TR:done"), _segment("b2", _PROSE)]
    assert retry_untranslated(_Dead(), segments) == 0
    assert segments[0].target == "TR:done"


def test_a_reply_that_echoed_the_source_is_retried() -> None:
    """Three translations of the same ten book pages each left a DIFFERENT paragraph in English
    (page 61 once, page 121 the next time): the model handed the source back unchanged, which is
    intermittent, not a paragraph it cannot translate. Asking again recovers it."""
    segments = [_segment("b1", _PROSE, target=_PROSE), _segment("b2", _PROSE, target="TR:done")]
    provider = _Recorder()

    assert retry_untranslated(provider, segments) == 1
    assert provider.calls == [["b1"]]
    assert segments[0].target == _fake_translation(_PROSE)


def test_an_echo_that_echoes_again_keeps_its_first_reply() -> None:
    class _Echo:
        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target=s.source) for s in segments]

    segments = [_segment("b1", _PROSE, target=_PROSE)]
    assert retry_untranslated(_Echo(), segments) == 0
    assert segments[0].target == _PROSE


def test_a_short_echo_is_retried_once_and_kept_if_it_echoes_again() -> None:
    """Book page 61: the heading "Decoder Expansion" came back in English. Two words is below the
    passthrough FLAG's minimum, because names legitimately translate to themselves - but asking
    once more costs one request, and a real name simply comes back the same and is kept."""
    heading = _segment("h", "Decoder Expansion", target="Decoder Expansion")
    name = _segment("n", "Form W-4", target="Form W-4")

    class _Translates:
        def translate(self, segments, **_kwargs):
            answers = {"Decoder Expansion": "Kod Cozucu Genisletme", "Form W-4": "Form W-4"}
            return [Segment(block_id=s.block_id, source=s.source, target=answers[s.source]) for s in segments]

    assert retry_untranslated(_Translates(), [heading, name]) == 1
    assert heading.target == "Kod Cozucu Genisletme"
    assert name.target == "Form W-4"


def test_a_reply_that_ran_on_into_the_next_paragraph_is_retried() -> None:
    """Book page 61: a figure caption came back with sentences of the neighbouring paragraph
    appended and was crushed into the caption box. Long relative to how this job's other replies
    compare with their sources - not a fixed ratio, which would be wrong for another language."""
    ordinary = [_segment(f"b{i}", _PROSE, target="T" * int(len(_PROSE) * 1.2)) for i in range(5)]
    caption_src = "Figure 2-3 A 3 x 8 decoder constructed with two 2 x 4 decoders."
    runaway = _segment("cap", caption_src, target="S" * (len(caption_src) * 6))

    class _Good:
        def translate(self, segments, **_kwargs):
            # A stand-in translation that keeps the source's numbers, as a real one must.
            return [Segment(block_id=s.block_id, source=s.source, target=_good(s.source)) for s in segments]

    assert retry_untranslated(_Good(), [*ordinary, runaway]) == 1
    assert runaway.target == _good(caption_src)
    assert all(seg.target.startswith("T") for seg in ordinary)


def test_a_reply_that_only_cleaned_up_the_source_is_retried() -> None:
    """Book page 251, pilot run: the model returned the paragraph still in English with its OCR
    noise corrected ("co s n thn" -> "communicate with"). Not identical, so nothing caught it.
    Most of a real translation's words are not the source's; most of this reply's words are."""
    source = "Simple CPU design examples are carried out in Chaps. 5 and 7. This chapter co s n thn memory stack."
    cleaned = "Simple CPU design examples are carried out in Chaps. 5 and 7. This chapter describes the memory stack."
    segment = _segment("p", source, target=cleaned)

    class _Translates:
        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target="Basit CPU tasarim ornekleri Bolum 5 ve 7'de verilmistir.") for s in segments]

    assert retry_untranslated(_Translates(), [segment]) == 1
    assert segment.target.startswith("Basit")


def test_a_translation_sharing_names_and_terms_is_not_taken_for_a_copy() -> None:
    source = "The CPU communicates with the ALU through buses and the register set."
    target = "CPU, ALU ile veri yollari ve register kumesi araciligiyla iletisim kurar."
    segment = _segment("t", source, target=target)
    provider = _Recorder()
    assert retry_untranslated(provider, [segment]) == 0
    assert provider.calls == []


def test_the_retry_is_sent_without_the_context_that_caused_the_echo() -> None:
    """Measured on gemma-4-e4b (`docs/campaign/JOURNAL.md`, echo experiment): four exercise items
    came back in English 3 times out of 3 when sent with their neighbouring paragraphs as context,
    and translated 3 times out of 3 without it. Retrying the same request cannot recover them."""

    class _EchoesWithContext:
        def __init__(self):
            self.saw_context = []

        def translate(self, segments, **_kwargs):
            out = []
            for s in segments:
                has_context = bool(s.context_before or s.context_after)
                self.saw_context.append(has_context)
                target = s.source if has_context else _fake_translation(s.source)
                out.append(Segment(block_id=s.block_id, source=s.source, target=target))
            return out

    segment = Segment(
        block_id="ex", source=_PROSE, target=_PROSE,
        context_before="1-13. Simplify the Boolean function", context_after="1-15. A majority function",
    )
    provider = _EchoesWithContext()
    assert retry_untranslated(provider, [segment]) == 1
    assert provider.saw_context == [False]
    assert segment.target == _fake_translation(_PROSE)
    assert segment.context_before, "the caller's segment keeps its context"


def test_an_echo_without_the_sources_markers_is_still_an_echo() -> None:
    source = "When the circuit is <0>disabled</0>, none of the outputs are <1>selected</1> at all."
    segment = _segment("m", source, target="When the circuit is disabled, none of the outputs are selected at all.")
    provider = _Recorder()
    assert retry_untranslated(provider, [segment]) == 1


def test_what_still_echoes_after_the_batch_retry_is_sent_alone() -> None:
    """Digital pilot, The Time Machine: a dialogue paragraph came back in English from the main
    pass AND the context-free batch retry, yet translated 24 of 24 times in isolation, alone or in
    parallel (docs/campaign/JOURNAL.md). The condition that makes the model echo it could not be
    reproduced; a request holding only that segment reliably did not."""

    class _EchoesInBatches:
        def __init__(self):
            self.batch_sizes = []

        def translate(self, segments, **_kwargs):
            self.batch_sizes.append(len(segments))
            return [
                Segment(block_id=s.block_id, source=s.source,
                        target=s.source if len(segments) > 1 else _fake_translation(s.source))
                for s in segments
            ]

    segments = [_segment("a", _PROSE, target=_PROSE), _segment("b", _PROSE + " Again.", target=_PROSE + " Again.")]
    provider = _EchoesInBatches()
    assert retry_untranslated(provider, segments) == 2
    assert provider.batch_sizes == [2, 1, 1]
    assert all(not s.target.startswith("An encoder") for s in segments)


def test_a_reply_that_lost_a_number_is_retried() -> None:
    source = "5.2.1 Basic Components of Program Policy ........ 27"
    segment = _segment("toc", source, target="Program Politikasinin Temel Bilesenleri ........ 27")

    class _KeepsNumbers:
        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target="5.2.1 Program Politikasinin Temel Bilesenleri ........ 27") for s in segments]

    assert retry_untranslated(_KeepsNumbers(), [segment]) == 1
    assert segment.target.startswith("5.2.1")


def test_a_number_lost_through_protection_is_retried_without_it() -> None:
    """Digital pilot 2, NIST: "(1)" in a glossary entry was held back as a placeholder, and the model
    dropped the placeholder 6 times out of 6. Sent as plain text, the same entry kept "(1)" 3 times
    out of 3 (docs/campaign/JOURNAL.md, number experiment). The last, one-at-a-time attempt for a
    reply that lost a number therefore bypasses the protection layer."""

    class _Plain:
        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target="(1) Bilgi ve olgular (2) Bilgi") for s in segments]

    class _Protected:
        inner = _Plain()

        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target="Bilgi ve olgular (2) Bilgi") for s in segments]

    source = "(1) Facts or ideas (2) Knowledge"
    segments = [_segment("a", source, target="Bilgi ve olgular (2) Bilgi"), _segment("b", "(3) More", target="Daha")]
    assert retry_untranslated(_Protected(), segments) >= 1
    assert segments[0].target.startswith("(1)")
