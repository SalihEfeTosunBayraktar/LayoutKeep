"""Tests for detecting a reply that is the source handed straight back.

The cases are taken from a measured run: gemma-4-e2b returned these exact English sentences
untranslated when context was sent, and the pipeline recorded all of them as successful
translations because `Segment.translated` only checks that `target` is non-empty.
"""

from __future__ import annotations

import pytest

from layoutkeep.core.docir import Segment
from layoutkeep.providers.passthrough import flag_passthrough, is_passthrough

# Verbatim from the measurement; the model returned each of these unchanged.
MEASURED_PASSTHROUGHS = [
    "\u201cThey lived on treacle,\u201d said the Dormouse, after thinking a minute or two.",
    (
    "\u201cWhat did they live on?\u201d said Alice, who always took a great interest in "
    "questions of eating and drinking."
    ),
    (
    "\u201cThey couldn\u2019t have done that, you know,\u201d Alice gently remarked; "
    "\u201cthey\u2019d have been ill.\u201d"
    ),
]


def _seg(source: str, target: str) -> Segment:
    seg = Segment(block_id="b1", source=source)
    seg.target = target
    return seg


@pytest.mark.parametrize("text", MEASURED_PASSTHROUGHS)
def test_a_sentence_returned_unchanged_is_caught(text: str) -> None:
    assert is_passthrough(_seg(text, text))


@pytest.mark.parametrize("text", MEASURED_PASSTHROUGHS)
def test_a_real_translation_is_not_caught(text: str) -> None:
    assert not is_passthrough(_seg(text, "Bu bir \u00e7eviridir ve kaynaktan farkl\u0131d\u0131r."))


@pytest.mark.parametrize(
    "source",
    [
        "Form W-4",          # a heading that is correctly identical
        "Alice",             # a bare proper noun
        "OMB No. 1545-0074",  # an identifier
        "63 Nm",             # protection answers this with its own source, on purpose
    ],
)
def test_short_identities_are_left_alone(source: str) -> None:
    """Identity is often correct. Flagging it would bury the real cases in noise."""
    assert not is_passthrough(_seg(source, source))


def test_whitespace_differences_do_not_hide_a_passthrough() -> None:
    text = "They lived on treacle, said the Dormouse."
    assert is_passthrough(_seg(text, "  They lived   on treacle,\nsaid the Dormouse.  "))


def test_an_empty_target_is_not_a_passthrough() -> None:
    """That is a different failure, already counted separately."""
    assert not is_passthrough(_seg("They lived on treacle, said the Dormouse.", ""))


def test_flagging_marks_segments_and_reports_the_count() -> None:
    segments = [
        _seg(MEASURED_PASSTHROUGHS[0], MEASURED_PASSTHROUGHS[0]),
        _seg(MEASURED_PASSTHROUGHS[1], "Ne ile ya\u015fad\u0131lar? diye sordu Alice."),
        _seg(MEASURED_PASSTHROUGHS[2], MEASURED_PASSTHROUGHS[2]),
    ]
    assert flag_passthrough(segments) == 2
    assert [s.needs_review for s in segments] == [True, False, True]
