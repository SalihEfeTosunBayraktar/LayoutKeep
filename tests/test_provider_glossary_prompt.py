"""A request carries the glossary terms its own segments contain, stated as a requirement.

The automatic glossary holds up to forty terms, and every request carried all of them on one line
("Use this glossary where the term appears: ..."). A small model given forty pairs to scan for one
or two that matter rendered the same term differently from page to page. A batch now sees only
the terms its text contains.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.providers.openai_compat import _build_messages

GLOSSARY = {"tokeniser": "belirteçleyici", "vocabulary": "kelime dağarcığı", "cake": "kek"}


def _system(segments):
    return _build_messages(segments, "en", "tr", GLOSSARY)[0]["content"]


def test_only_the_terms_in_the_batch_are_sent():
    system = _system([Segment(block_id="a", source="The tokeniser splits words.")])
    assert "belirteçleyici" in system
    assert "kelime dağarcığı" not in system and "kek" not in system


def test_a_term_is_found_whatever_its_case():
    assert "belirteçleyici" in _system([Segment(block_id="a", source="Tokeniser output")])


def test_no_matching_term_sends_no_glossary_line():
    system = _system([Segment(block_id="a", source="Nothing relevant here.")])
    assert "belirteçleyici" not in system and "glossary" not in system.lower()
