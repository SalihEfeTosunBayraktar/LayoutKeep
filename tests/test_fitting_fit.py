"""Tests for the three-layer fit strategy. No PDF, no PyMuPDF, no network: `measure` and
`retranslate` are fakes, exactly the seam fit.py is designed around (docs/CONTRACT.md D2/D3).

Fakes mirror `layoutkeep.writers.pdf_writer.measure_fit`'s real signature: called as
`measure(text, style, bbox, scale_low=..., rotation=...)`, returning a plain `(fits, scale)`
tuple. Rotation-specific behaviour (the geometry itself) is covered separately in
`test_fitting_rotation.py`; these fakes just need to accept the keyword so `fit_segment`'s
always-pass-rotation call doesn't break them.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Segment, Style
from layoutkeep.fitting.fit import FitLayer, FitMode, fit_segment, summarize

BOX = BBox(0, 0, 100, 100)
STYLE = Style(size=12.0)


def _segment(target: str) -> Segment:
    return Segment(block_id="b1", source="source text", target=target)


def test_layer1_fits_as_is():
    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 1.0

    result = fit_segment(_segment("short"), STYLE, BOX, measure)
    assert result.layer is FitLayer.AS_IS
    assert result.scale == 1.0
    assert result.needs_review is False


def test_layer2_fits_after_shrinking():
    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 0.9

    result = fit_segment(_segment("a bit longer"), STYLE, BOX, measure)
    assert result.layer is FitLayer.SHRUNK
    assert result.scale == 0.9


def test_layer3_retranslation_is_triggered_and_succeeds():
    calls = []

    def measure(text, style, bbox, scale_low, rotation=0.0):
        # Only the shorter, re-translated text fits.
        return (text == "short"), scale_low

    def retranslate(segment, max_len):
        calls.append((segment.block_id, max_len))
        return "short"

    result = fit_segment(
        _segment("way too long to fit in the box"),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
    )
    assert result.layer is FitLayer.RETRANSLATED
    assert result.text == "short"
    assert calls == [("b1", calls[0][1])]  # retranslate was called exactly once, with our block_id


def test_retranslate_never_called_when_first_measure_fits():
    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 1.0

    def retranslate(segment, max_len):
        raise AssertionError("retranslate must not be called when the text already fits")

    fit_segment(_segment("fits fine"), STYLE, BOX, measure, retranslate=retranslate)


def test_layer4_strict_mode_accepts_overflow_and_flags_review():
    def measure(text, style, bbox, scale_low, rotation=0.0):
        return False, scale_low

    result = fit_segment(
        _segment("still too long"), STYLE, BOX, measure, mode=FitMode.STRICT
    )
    assert result.layer is FitLayer.OVERFLOW
    assert result.needs_review is True
    assert result.reflow is False


def test_layer4_reflow_mode_reports_reflow_instead_of_flagging_review():
    def measure(text, style, bbox, scale_low, rotation=0.0):
        return False, scale_low

    result = fit_segment(
        _segment("still too long"), STYLE, BOX, measure, mode=FitMode.REFLOW
    )
    assert result.layer is FitLayer.OVERFLOW
    assert result.needs_review is False
    assert result.reflow is True


def test_char_budget_callback_is_used_when_provided():
    seen_budget = {}

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return (text == "ok"), scale_low

    def retranslate(segment, max_len):
        seen_budget["value"] = max_len
        return "ok"

    def char_budget(style, bbox, scale):
        return 7

    fit_segment(
        _segment("too long"),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=char_budget,
    )
    assert seen_budget["value"] == 7


def test_measure_is_called_with_scale_low_as_keyword():
    # pdf_writer.measure_fit declares `scale_low` keyword-only; fit.py must call it that way.
    def measure(text, style, bbox, *, scale_low, rotation=0.0):
        return True, 1.0

    result = fit_segment(_segment("short"), STYLE, BOX, measure)
    assert result.layer is FitLayer.AS_IS


def test_summarize_counts_each_layer():
    def fits_at(scale):
        return lambda text, style, bbox, scale_low, rotation=0.0: (True, scale)

    def never_fits(text, style, bbox, scale_low, rotation=0.0):
        return False, scale_low

    results = [
        fit_segment(_segment("a"), STYLE, BOX, fits_at(1.0)),
        fit_segment(_segment("b"), STYLE, BOX, fits_at(0.9)),
        fit_segment(_segment("c"), STYLE, BOX, never_fits, mode=FitMode.STRICT),
    ]
    counts = summarize(results)
    assert counts == {
        "as_is": 1,
        "shrunk": 1,
        "retranslated": 0,
        "expanded": 0,
        "overflow": 1,
    }


# -- direction 2: under-fill -> ask for a longer rendering, never at the cost of overflow --


def test_expansion_triggered_when_translation_fills_very_little_of_the_box():
    """The product's promise is a translation that occupies the box like the original did.
    EN->TR comes back as short as 0.64x; when that leaves the box mostly empty, a longer
    rendering must be requested and used."""

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 1.0

    def retranslate(segment, max_len):
        return "bu bir considerably longer translation that fills the box properly"

    result = fit_segment(
        _segment("kısa"),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 80,
    )
    assert result.layer is FitLayer.EXPANDED
    assert result.text != "kısa"
    assert result.scale == 1.0
    assert result.needs_review is False


def test_no_expansion_when_fill_is_already_reasonable():
    calls = []

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 1.0

    def retranslate(segment, max_len):
        calls.append(max_len)
        return "daha uzun"

    result = fit_segment(
        _segment("x" * 65),  # 65/80 = 81% of the budget - above the 0.75 floor
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 80,
    )
    assert result.layer is FitLayer.AS_IS
    assert calls == []  # no request spent


def test_expansion_never_trades_a_fit_for_an_overflow():
    """A longer candidate that does not fit must be rejected - the current text is kept."""

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return len(text) <= 10, 1.0

    def retranslate(segment, max_len):
        return "çok daha uzun bir çeviri"  # overflows

    result = fit_segment(
        _segment("kısa"),  # fits (4 <= 10)
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 80,
    )
    assert result.layer is FitLayer.AS_IS
    assert result.text == "kısa"


def test_expansion_reports_the_accepted_texts_real_scale():
    """The accepted longer text may only fit shrunk. The result must carry that shrunk
    scale - reporting the original's 1.0 makes the writer print the longer text at full size
    and the expansion becomes an overflow in rendering (fit e2e pass observation)."""

    def measure(text, style, bbox, scale_low, rotation=0.0):
        # short text fits at full size; a longer candidate only fits at 0.88
        if len(text) > 20:
            return True, 0.88
        return True, 1.0

    def retranslate(segment, max_len):
        return "çok daha uzun bir çeviri metni ki kutuya ancak küçülerek sığar"

    result = fit_segment(
        _segment("kısa"),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 80,
    )
    assert result.layer is FitLayer.EXPANDED
    assert result.text.startswith("çok daha uzun")
    assert result.scale == 0.88  # not the stale 1.0 from the short text


def test_expansion_keeps_an_earlier_improvement_when_the_model_runs_out():
    """Round 1 improves the fill, round 2 overflows: the round-1 text must be kept, not
    thrown away - iterating toward the original look must never end worse than it started."""

    offered = ["orta uzunlukta bir çeviri metni burada", "çok daha uzun taşan çeviri metni buraya gelir"]
    calls = iter(offered)

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return len(text) <= 38, 1.0

    def retranslate(segment, max_len):
        return next(calls)

    result = fit_segment(
        _segment("kısa"),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 80,
    )
    assert result.layer is FitLayer.EXPANDED
    assert result.text == "orta uzunlukta bir çeviri metni burada"


def test_no_expansion_without_a_char_budget_callback():
    """Without an honest budget there is no honest 'how full is the box' - the engine must
    not guess from source length, which would flag ordinary 0.9x variation."""

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return True, 1.0

    def retranslate(segment, max_len):
        raise AssertionError("must not ask for a longer text without a budget")

    result = fit_segment(_segment("kısa"), STYLE, BOX, measure, retranslate=retranslate)
    assert result.layer is FitLayer.AS_IS


# -- iterative direction 1: shrink until it fits -------------------------------------------------


def test_retranslation_iterates_with_a_tightening_budget():
    """A model that keeps its reply above the shrinking budget gets a firmer target each
    round: the next request aims strictly below the length that just failed to fit."""

    budgets = []

    def measure(text, style, bbox, scale_low, rotation=0.0):
        return len(text) <= 15, 1.0

    def retranslate(segment, max_len):
        budgets.append(max_len)
        return "y" * max(10, max_len - 2)  # respects the budget but still overflows

    result = fit_segment(
        _segment("y" * 40),
        STYLE,
        BOX,
        measure,
        retranslate=retranslate,
        char_budget=lambda style, bbox, scale: 30,
    )
    assert result.layer is FitLayer.OVERFLOW  # 3 rounds were not enough to reach <= 15
    assert budgets == [30, 27, 24]  # each round strictly below the failed length
    assert len(result.text) <= 26  # kept the best (shortest) attempt
