"""Repeated text is translated once, and the same source never reads two ways in one document.

Measured over the recorded held-out runs: a quarter to a third of a form's translatable segments
are repetitions (irs_p505 537 of 2,144; irs_i1040gi 252 of 737), and the repeats did not come back
the same - irs_p505 held 80 groups whose identical source had more than one translation, IRS Form
1040's instructions wording "Married filing separately" three ways and "Head of household" two.
These tests hold the two mechanisms: `providers/dedupe.py` (ask once, answer everywhere) and
`core/repeats.py` (make what is already written agree).
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.core.repeats import share_key, unify_repeats
from layoutkeep.providers.dedupe import DedupeProvider

_REPEATED = "Need more information or forms? Visit IRS.gov."
_OTHER = "Qualified tips are taxable income."


class _Counter:
    """A provider that translates what it is asked and remembers what that was."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
        self.calls.append([s.block_id for s in segments])
        return [
            Segment(block_id=s.block_id, source=s.source, target=f"TR::{s.source}") for s in segments
        ]


def _seg(block_id: str, source: str, target: str = "") -> Segment:
    return Segment(block_id=block_id, source=source, target=target)


def test_repeated_text_is_asked_for_once_and_answered_everywhere() -> None:
    inner = _Counter()
    segments = [_seg("b1", _REPEATED), _seg("b2", _OTHER), _seg("b3", _REPEATED)]

    out = DedupeProvider(inner).translate(segments, "en", "tr")

    assert inner.calls == [["b1", "b2"]], "the repeat must not be sent again"
    assert [s.target for s in out] == [f"TR::{_REPEATED}", f"TR::{_OTHER}", f"TR::{_REPEATED}"]
    assert [s.block_id for s in out] == ["b1", "b2", "b3"], "one segment per input, in order"


def test_the_repeat_keeps_its_own_identity_and_context() -> None:
    inner = _Counter()
    first = Segment(block_id="b1", source=_REPEATED, context_before="above one")
    repeat = Segment(block_id="b9", source=_REPEATED, context_before="above nine", max_len=99)

    out = DedupeProvider(inner).translate([first, repeat], "en", "tr")

    assert out[1].block_id == "b9" and out[1].context_before == "above nine"
    assert out[1].max_len == 99
    assert out[1].target == out[0].target


def test_whitespace_and_case_do_not_make_two_texts() -> None:
    inner = _Counter()
    segments = [_seg("b1", "Need more information\nor forms?"), _seg("b2", "need  more information or forms?")]

    out = DedupeProvider(inner).translate(segments, "en", "tr")

    assert len(inner.calls[0]) == 1
    assert out[0].target == out[1].target


def test_one_and_two_word_texts_are_never_shared() -> None:
    """Measured on the same runs: "where" came back as "nerede" and as "ner"; sharing those would
    spread one sense across the document to save nothing."""
    inner = _Counter()
    segments = [_seg("b1", "where"), _seg("b2", "where"), _seg("b3", "ours"), _seg("b4", "ours")]

    DedupeProvider(inner).translate(segments, "en", "tr")

    assert inner.calls == [["b1", "b2", "b3", "b4"]]


def test_sharing_can_be_turned_off() -> None:
    inner = _Counter()
    segments = [_seg("b1", _REPEATED), _seg("b2", _REPEATED)]

    DedupeProvider(inner, enabled=False).translate(segments, "en", "tr")

    assert inner.calls == [["b1", "b2"]]


def test_a_segment_with_no_reply_is_not_filled_from_its_repeat() -> None:
    class _Silent(_Counter):
        def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
            self.calls.append([s.block_id for s in segments])
            return [
                Segment(block_id=s.block_id, source=s.source, needs_review=True) for s in segments
            ]

    out = DedupeProvider(_Silent()).translate([_seg("b1", _REPEATED), _seg("b2", _REPEATED)], "en", "tr")
    assert [s.target for s in out] == ["", ""]
    assert all(s.needs_review for s in out)


def test_share_key_ignores_whitespace_and_case_and_refuses_short_text() -> None:
    assert share_key("Need  more\ninformation") == share_key("need more information")
    assert share_key("where") is None
    assert share_key("ours is") is None


# -- the sweep over what is already written ---------------------------------------------


def test_the_minority_is_rewritten_to_the_majority() -> None:
    segments = [
        _seg("b1", _REPEATED, "Daha fazla bilgi veya form için IRS.gov'u ziyaret edin."),
        _seg("b2", _REPEATED, "Daha fazla bilgi veya form için IRS.gov'u ziyaret edin."),
        _seg("b3", _REPEATED, "Bilgi veya form mu lazım? IRS.gov."),
    ]

    report = unify_repeats(segments, "tr")

    assert report["groups"] == 1 and report["rewritten"] == 1
    assert segments[2].target == segments[0].target


def test_a_variant_that_lost_a_number_is_never_chosen() -> None:
    """"Sayfa 20-24" keeps the source's numbers; "Sayfalar arası" does not. Consistency must not
    be bought with a lost value."""
    source = "See pages 20 through 24 for the worksheet."
    segments = [
        _seg("b1", source, "Sayfalar arası çalışma sayfasına bakın."),
        _seg("b2", source, "Sayfalar arası çalışma sayfasına bakın."),
        _seg("b3", source, "Çalışma sayfası için sayfa 20-24'e bakın."),
    ]

    unify_repeats(segments, "tr")

    assert segments[0].target == segments[2].target
    assert "20" in segments[0].target


def test_a_tie_goes_to_the_one_the_document_used_first() -> None:
    segments = [_seg("b1", _REPEATED, "ilk"), _seg("b2", _REPEATED, "ikinci")]
    unify_repeats(segments, "tr")
    assert segments[0].target == segments[1].target == "ilk"


def test_short_texts_with_different_translations_are_left_alone() -> None:
    segments = [_seg("b1", "where", "nerede"), _seg("b2", "where", "ner")]
    report = unify_repeats(segments, "tr")
    assert report["rewritten"] == 0
    assert segments[1].target == "ner"


def test_agreement_costs_nothing() -> None:
    segments = [_seg("b1", _REPEATED, "aynı"), _seg("b2", _REPEATED, "aynı")]
    report = unify_repeats(segments, "tr")
    assert report == {"groups": 0, "rewritten": 0, "examples": []}


# -- the CLI's own chain ---------------------------------------------------------------


def _translate_args(**overrides):
    from argparse import Namespace

    base = {
        "provider": "fake", "memory": None, "no_repeats": False, "base_url": None,
        "model": None, "api_key": None, "timeout": None,
    }
    base.update(overrides)
    return Namespace(**base)


def test_the_cli_shares_repeats_by_default() -> None:
    from layoutkeep.cli import _build_provider

    provider, memory = _build_provider(_translate_args())
    assert memory is None

    provider.translate([_seg("b1", _REPEATED), _seg("b2", _REPEATED)], "en", "tr")

    assert _dedupe_stats_of(provider)["saved"] == 1


def test_no_repeats_turns_it_off() -> None:
    from layoutkeep.cli import _build_provider

    provider, _ = _build_provider(_translate_args(no_repeats=True))
    provider.translate([_seg("b1", _REPEATED), _seg("b2", _REPEATED)], "en", "tr")

    assert _dedupe_stats_of(provider)["saved"] == 0


def _dedupe_stats_of(provider) -> dict[str, int]:
    from layoutkeep.cli import _dedupe_stats

    return _dedupe_stats(provider)


def test_a_capped_repeat_is_answered_within_its_budget() -> None:
    """The fit pass caps a shorten request (`max_len`); the canonical reply, produced without a
    cap, can be longer than it - a capped asker then goes to the provider itself rather than
    receiving a translation that ignores its budget (the same rule `providers/cached.py` applies
    to a memory hit)."""

    class _ShortProvider:
        def __init__(self) -> None:
            self.caps: list[int | None] = []

        def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
            self.caps += [s.max_len for s in segments]
            return [
                Segment(block_id=s.block_id, source=s.source, target=f"TR::{s.source}",
                        max_len=s.max_len)
                for s in segments
            ]

    inner = _ShortProvider()
    first = Segment(block_id="b1", source=_REPEATED)  # uncapped: gets the long answer
    repeat = Segment(block_id="b9", source=_REPEATED, max_len=10)  # capped: too long, asks itself

    out = DedupeProvider(inner).translate([first, repeat], "en", "tr")

    assert inner.caps == [None, 10], "the second request is the capped repeat, which the shared answer could not serve"
    assert out[1].max_len == 10
    # The uncapped occurrence still got the shared answer.
    assert out[0].target == f"TR::{_REPEATED}"
