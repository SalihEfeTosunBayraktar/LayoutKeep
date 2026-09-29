"""A segment that missed a glossary term is asked once more, with only the terms it missed.

The term check flagged a miss and left it for a reviewer; the same term then read two ways in one
document. One more request - a single segment with its own missing terms stated as a requirement -
is cheap, and the reply is kept only when it honours every term it was asked for.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.glossary import Glossary, reask_misses


class _Provider:
    def __init__(self, replies):
        self.replies = replies
        self.asked = []

    def translate(self, segments, *, src_lang, tgt_lang, glossary=None):
        self.asked.append((tuple(s.block_id for s in segments), dict(glossary or {})))
        for segment in segments:
            segment.target = self.replies.get(segment.block_id, segment.target)
        return segments


def _flagged(glossary):
    segments = [
        Segment(block_id="a", source="The tokeniser is fast.", target="Tokenizer hızlıdır."),
        Segment(block_id="b", source="A cake.", target="Bir kek."),
    ]
    return glossary.verify(segments)[0]


def test_a_miss_is_asked_again_with_only_its_missing_term_and_the_fix_is_kept():
    glossary = Glossary({"tokeniser": "belirteçleyici", "cake": "kek"})
    segments = _flagged(glossary)
    provider = _Provider({"a": "Belirteçleyici hızlıdır."})

    fixed = reask_misses(glossary, provider, segments, src_lang="en", tgt_lang="tr")

    assert fixed == 1
    assert provider.asked == [(("a",), {"tokeniser": "belirteçleyici"})]
    assert segments[0].target == "Belirteçleyici hızlıdır." and not segments[0].needs_review


def test_a_reply_that_still_misses_the_term_is_not_kept():
    glossary = Glossary({"tokeniser": "belirteçleyici"})
    segments = _flagged(glossary)
    provider = _Provider({"a": "Tokenleştirici hızlıdır."})

    assert reask_misses(glossary, provider, segments, src_lang="en", tgt_lang="tr") == 0
    assert segments[0].target == "Tokenizer hızlıdır." and segments[0].needs_review
