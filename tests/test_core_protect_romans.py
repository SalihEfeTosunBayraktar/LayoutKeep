"""The Roman-numeral rule is a setting, and it does what the setting says.

The rule exists because of a measured loss: the statistics book's contents page came back with its
running-head page number "xiii" translated into words ("on üç"). It is on by default - a page
number is a fact - but it is also the kind of protection a user may want to trade away per
document, so it lives in the developer settings next to the other switches.
"""

from __future__ import annotations

import pytest

from layoutkeep.core import tunables
from layoutkeep.core.protect import PROTECT_ROMANS_KEY, protect


@pytest.fixture(autouse=True)
def _restore() -> None:
    before = tunables.get(PROTECT_ROMANS_KEY)
    yield
    tunables.set_value(PROTECT_ROMANS_KEY, before)


def test_on_by_default_the_page_number_is_protected() -> None:
    tunables.set_value(PROTECT_ROMANS_KEY, True)
    result = protect("Contents xiii")
    assert "xiii" not in result.text
    assert list(result.literals.values()) == ["xiii"]


def test_switched_off_the_number_is_left_to_the_model() -> None:
    tunables.set_value(PROTECT_ROMANS_KEY, False)
    result = protect("Contents xiii")
    assert result.text == "Contents xiii"
    assert result.literals == {}


def test_a_lone_i_is_never_protected() -> None:
    """An English pronoun, not a numeral - the rule needs two characters for this reason."""
    tunables.set_value(PROTECT_ROMANS_KEY, True)
    assert protect("I went home").literals == {}


def test_units_that_look_like_numerals_are_left_alone() -> None:
    """`mm` is two thousand to a numeral parser and a millimetre to everyone else."""
    tunables.set_value(PROTECT_ROMANS_KEY, True)
    result = protect("a 5 mm bolt")
    assert list(result.literals.values()) == ["5 mm"]  # the measurement, not the "mm" alone


def test_upper_case_part_markers_count_too() -> None:
    tunables.set_value(PROTECT_ROMANS_KEY, True)
    result = protect("CHAPTER IV begins")
    assert "IV" in result.literals.values()
