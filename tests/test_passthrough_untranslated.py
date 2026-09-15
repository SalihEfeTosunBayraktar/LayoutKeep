"""A segment that never came back leaves source-language text in the output, silently.

`flag_passthrough` catches the model handing its input back verbatim. It cannot catch the other
way the same thing happens: a segment whose reply never arrived at all keeps an empty `target`,
the writer falls back to the block's existing text, and the output document quietly contains a
paragraph of the source language.

Measured on `computer-systems-Architecture.pdf`: the CLI reported `translated 193/210` and said
nothing else, while 11 of 43 prose segments - a quarter of the running text - were still English
in the output PDF. `193/210` is the only hint, and it reads like a rounding loss rather than
"seventeen paragraphs of your document were not translated".
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.passthrough import flag_untranslated


def _segment(source: str, target: str = "") -> Segment:
    return Segment(block_id="b1", source=source, target=target)


def test_missing_reply_is_flagged() -> None:
    segment = _segment("An encoder is a digital circuit that performs the inverse operation.")
    assert flag_untranslated([segment]) == 1
    assert segment.needs_review is True
    assert segment.review_reason


def test_translated_segment_is_left_alone() -> None:
    segment = _segment("An encoder is a digital circuit.", target="Bir kodlayici bir devredir.")
    assert flag_untranslated([segment]) == 0
    assert segment.needs_review is False


def test_data_only_segment_is_not_flagged() -> None:
    """Protection answers these without a request on purpose - an empty or echoed target here is
    the designed behaviour, not a lost reply, and flagging them would bury the real ones."""
    segment = _segment("10000000111")
    assert flag_untranslated([segment]) == 0
    assert segment.needs_review is False


def test_an_existing_review_reason_is_not_overwritten() -> None:
    """Whatever already flagged the segment knows more about why than this does."""
    segment = _segment("An encoder is a digital circuit that performs the inverse operation.")
    segment.needs_review = True
    segment.review_reason = "OCR guveni dusuk (0.41)"
    assert flag_untranslated([segment]) == 1
    assert segment.review_reason == "OCR guveni dusuk (0.41)"
