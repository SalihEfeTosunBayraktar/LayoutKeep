"""Which language pairs the application calls measured, and with what numbers.

WHY THIS EXISTS: 0.9.10 is the first build whose EN->TR and TR->EN runs cleared all three bars on
the bench. The setup screen says so next to the language boxes, and says just as plainly when a
pair has not been measured - one table decides both, so they cannot disagree.
"""

from __future__ import annotations

from layoutkeep.core.capabilities import MEASURED_LANGUAGE_PAIRS, language_pair_measurement


def test_both_directions_between_english_and_turkish_are_measured():
    assert language_pair_measurement("en", "tr")[0] == ("en", "tr")
    assert language_pair_measurement("tr", "en")[0] == ("tr", "en")


def test_every_measured_pair_clears_the_three_bars():
    for numbers in MEASURED_LANGUAGE_PAIRS.values():
        assert min(float(numbers[bar]) for bar in ("quality", "consistency", "layout")) > 90


def test_another_pair_is_unmeasured():
    assert language_pair_measurement("en", "de") is None
    assert language_pair_measurement("de", "tr") is None


def test_an_auto_detected_source_counts_as_the_measured_pair_for_its_target():
    assert language_pair_measurement("auto", "tr")[0] == ("en", "tr")
    assert language_pair_measurement("auto", "en")[0] == ("tr", "en")
    assert language_pair_measurement("auto", "de") is None
