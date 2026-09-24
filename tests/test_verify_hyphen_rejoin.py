"""A word the writer hyphenated at a line end is still the word the block holds.

The German soft hyphens (core/hyphenate.py) break "Steuererklärungen" into "Steuer-" and
"erklärungen" on two lines; read as two words neither matched the block, and the block was
reported as not on the page (L3: 5 false findings on one IRS form).
"""

from __future__ import annotations

from layoutkeep.verify import _rejoined


def _w(text, block, line):
    return (0, 0, 0, 0, text, block, line, 0)


def test_a_word_broken_at_a_line_end_is_joined():
    drawn = [_w("Die", 0, 0), _w("Steuer-", 0, 0), _w("erklärungen", 0, 1), _w("sind", 0, 1)]
    assert _rejoined(drawn) == ["Die", "Steuererklärungen", "sind"]


def test_a_hyphen_inside_a_line_is_left_alone():
    drawn = [_w("US-", 0, 0), _w("Handel", 0, 0), _w("Ende-", 0, 0)]
    assert _rejoined(drawn) == ["US-", "Handel", "Ende-"]


def test_a_broken_word_with_a_bracket_is_joined():
    drawn = [_w("(Dollar-", 0, 0), _w("betrag)**", 0, 1)]
    assert _rejoined(drawn) == ["(Dollarbetrag)**"]
