"""Trimming the context: off by default, and it keeps the text nearest the segment.

WHY THIS EXISTS: measured on the Gutenberg book, the neighbouring context is 199% of the text being
translated and two thirds of every request, and an A/B on 12 segments put the cost in wall-clock
terms too - 4,899 characters and 53.9s with context against 1,645 characters and 19.7s without. The
median context is only 193 characters; the waste is in the long tail (longest 3,781). So the cap is
a number a user can set, it defaults to 0 (no cap, today's behaviour), and it clips from the middle
outwards - the previous block keeps its tail, the next keeps its head - because the text touching the
segment is the part that carries pronouns and terminology.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core import tunables
from layoutkeep.core.docir import load_project, segments_from_document

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "_artifacts/heldout/live/gutenberg_56464/gutenberg_56464.lkproj"
_KEY = "translation.context_max_chars"

pytestmark = pytest.mark.skipif(not BOOK.exists(), reason="the recorded Gutenberg run is not on disk")


def _contexts() -> list[tuple[str, str]]:
    doc = load_project(BOOK)
    return [(s.context_before, s.context_after) for s in segments_from_document(doc)]


def test_zero_means_no_cap_and_the_default_is_four_hundred() -> None:
    """0 is the old behaviour; 400 is the default and a decision, so it is pinned here.

    The cap defaults to 400 because a measurement chose it (D-005 in docs/DECISIONS.md): it cuts 26%
    of what is sent while leaving the median context of 193 characters untouched. Flipping it back
    without repeating that measurement should fail rather than pass silently.
    """
    assert tunables.definition(_KEY).default == 400

    was = tunables.get(_KEY)
    tunables.set_value(_KEY, 0)
    try:
        pairs = _contexts()
    finally:
        tunables.set_value(_KEY, was)

    assert pairs, "the recorded run should yield segments"
    assert max(len(b) for b, _ in pairs) > 200, "with no cap the long contexts must still be there"


def test_a_cap_keeps_the_end_of_what_came_before_and_the_start_of_what_follows() -> None:
    cap = 120
    was = tunables.get(_KEY)
    tunables.set_value(_KEY, cap)
    try:
        capped = _contexts()
    finally:
        tunables.set_value(_KEY, was)
    # "full" must mean uncapped whatever the default happens to be: this test is about clipping,
    # not about which default is in force.
    tunables.set_value(_KEY, 0)
    try:
        full = _contexts()
    finally:
        tunables.set_value(_KEY, was)

    assert len(capped) == len(full)
    for (b_cap, a_cap), (b_full, a_full) in zip(capped, full, strict=True):
        assert len(b_cap) <= cap and len(a_cap) <= cap
        if len(b_full) > cap:
            assert b_cap == b_full[-cap:], "the previous block must keep its tail"
        if len(a_full) > cap:
            assert a_cap == a_full[:cap], "the next block must keep its head"

    sent_full = sum(len(b) + len(a) for b, a in full)
    sent_capped = sum(len(b) + len(a) for b, a in capped)
    assert sent_capped < sent_full / 2, f"the cap should cut the bulk: {sent_capped} vs {sent_full}"
