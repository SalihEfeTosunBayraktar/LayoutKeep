"""One inconsistency is counted once, not once per phrase that happens to contain it.

WHY THIS EXISTS: the consistency bar sampled "Hawk fed upon", "Hawk fed" and "fed upon" as three terms
from the same two sentences, and "Fungi" and "fungi" as two. One disagreement between two renderings
then counted three times against the document. A term is left out when a term already kept contains
it and was sampled from the same sentences, or when it differs from a kept term only in case.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "audit"))

from term_consistency import _distinct

A = ("The Hawk fed upon it.", "x")
B = ("A Hawk fed upon them.", "y")
C = ("Reference values differ.", "z")


def test_a_phrase_inside_a_kept_term_from_the_same_sentences_is_dropped():
    found = {"Hawk fed upon": [A, B], "Hawk fed": [A, B], "fed upon": [A, B]}

    assert list(_distinct(found)) == ["Hawk fed upon"]


def test_a_term_that_only_differs_in_case_is_dropped():
    assert list(_distinct({"Fungi": [A, B], "fungi": [A, B]})) == ["Fungi"]


def test_a_shorter_term_seen_in_other_sentences_too_is_kept():
    found = {"Standard Reference": [A, B], "Reference": [A, C]}

    assert list(_distinct(found)) == ["Standard Reference", "Reference"]
