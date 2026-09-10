"""Tests for job-size estimation and progress-by-characters (core/estimate.py).

Pure arithmetic over Segment source/target lengths - the numbers the UI shows before
a job ("~X tokens") and while it runs (the character progress bar). No network.
"""

from __future__ import annotations

from layoutkeep.core.docir import Segment
from layoutkeep.core.estimate import (
    JobEstimate,
    chars_per_token,
    estimate_job,
    expansion_ratio,
    measured_expansion,
    progress_by_chars,
)


def _seg(source: str, target: str = "", *, ctx_before: str = "", ctx_after: str = "") -> Segment:
    return Segment(
        block_id="b",
        source=source,
        target=target,
        context_before=ctx_before,
        context_after=ctx_after,
    )


def test_chars_per_token_known_and_default():
    assert chars_per_token("en") == 4.0
    assert chars_per_token("tr") == 3.0  # agglutinative -> more pieces
    assert chars_per_token(None) == 3.5
    assert chars_per_token("xx-nonexistent") == 3.5


def test_expansion_ratio_turkish_is_measured_shorter():
    # Measured: EN->TR prose is 0.93x, not the >1.0 literature guess.
    assert expansion_ratio("tr") == 0.93
    assert expansion_ratio("de") == 1.30
    assert expansion_ratio(None) == 1.15


def test_estimate_job_counts_only_source_chars_as_output_base():
    segs = [_seg("abcdefgh", ctx_before="BBBB", ctx_after="AAAA")]  # 8 src + 8 ctx
    est = estimate_job(segs, "en", "tr")
    assert isinstance(est, JobEstimate)
    assert est.segments == 1
    assert est.source_chars == 8
    # Context is billed (input side) but is not translation output.
    assert est.assumed_expansion == 0.93
    assert est.output_tokens == round(8 * 0.93 / 3.0)
    # Input tokens include context; without it they shrink.
    est_no_ctx = estimate_job(segs, "en", "tr", include_context=False)
    assert est_no_ctx.input_tokens < est.input_tokens
    assert est_no_ctx.source_chars == est.source_chars


def test_total_tokens_sums_input_and_output():
    segs = [_seg("aaaa")]  # 4 en chars
    est = estimate_job(segs, "en", "tr")
    assert est.total_tokens == est.input_tokens + est.output_tokens


def test_progress_by_chars_source_side():
    segs = [_seg("0123456789", "çeviri"), _seg("abcde", ""), _seg("xy", "q")]
    done, total = progress_by_chars(segs)
    assert total == 17
    assert done == 12  # first (10) + third (2); second untranslated
    assert done <= total


def test_progress_zero_when_nothing_translated():
    segs = [_seg("abc", ""), _seg("def", "")]
    assert progress_by_chars(segs) == (0, 6)


def test_measured_expansion_none_until_translated():
    assert measured_expansion([_seg("abc", "")]) is None
    assert measured_expansion([]) is None


def test_measured_expansion_real_ratio():
    segs = [_seg("aaaa", "aa"), _seg("bbbbbbbb", "bbbb")]  # 0.5x both
    assert measured_expansion(segs) == 0.5
