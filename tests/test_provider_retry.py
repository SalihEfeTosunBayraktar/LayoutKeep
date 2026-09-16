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
            target = "" if seg.block_id in self.fails else f"TR:{seg.source}"
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
    assert segments[1].target == f"TR:{_PROSE}"
    assert segments[2].target == f"TR:{_PROSE}"


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
    assert segments[0].target == f"TR:{_PROSE}"


def test_an_echo_that_echoes_again_keeps_its_first_reply() -> None:
    class _Echo:
        def translate(self, segments, **_kwargs):
            return [Segment(block_id=s.block_id, source=s.source, target=s.source) for s in segments]

    segments = [_segment("b1", _PROSE, target=_PROSE)]
    assert retry_untranslated(_Echo(), segments) == 0
    assert segments[0].target == _PROSE


def test_a_short_identical_reply_is_not_retried() -> None:
    """A heading or a name legitimately translates to itself."""
    segments = [_segment("b1", "Form W-4", target="Form W-4")]
    provider = _Recorder()
    assert retry_untranslated(provider, segments) == 0
    assert provider.calls == []
