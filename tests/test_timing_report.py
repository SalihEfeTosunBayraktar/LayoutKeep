"""The phase breakdown a run can leave beside its output.

The report exists to answer "where did the time go" after the fact, so these check the numbers and
the file, not the styling: the percentages have to add up, a phase list is never empty, and the page
lands where it was asked to land.
"""

from __future__ import annotations

from layoutkeep.core import tunables
from layoutkeep.core.timing import PhaseTimer, TimingReport


def _report() -> TimingReport:
    report = TimingReport(document="academic_paper_10.pdf", requests=91)
    timer = PhaseTimer(report)
    with timer.phase("read", "10 pages"):
        pass
    with timer.phase("segment"):
        pass
    with timer.phase("translate", "731 segments"):
        pass
    return report


def test_phases_add_up_and_each_has_a_share():
    report = _report()
    assert [p.name for p in report.phases] == ["read", "segment", "translate"]
    assert report.total > 0
    assert abs(sum(report.percent(p) for p in report.phases) - 100.0) < 0.001


def test_the_report_names_the_document_and_the_work():
    html = _report().as_html()
    for fragment in ("read", "segment", "translate", "731 segments", "academic_paper_10.pdf"):
        assert fragment in html, f"{fragment!r} missing from the report"
    assert "91 requests" in html
    assert "<script" not in html, "the report must stay self-contained"


def test_a_phase_reports_the_seconds_it_ran_for():
    timer = PhaseTimer(TimingReport())
    with timer.phase("translate"):
        pass
    (phase,) = timer.report.phases
    assert phase.name == "translate"
    assert phase.seconds >= 0.0


def test_the_report_is_written_where_it_is_asked_to_land(tmp_path):
    out = tmp_path / "book.tr.pdf"
    target = out.with_name(f"{out.stem}.timing.html")
    written = _report().write_html(target)
    assert written == target
    assert written.exists()
    assert "translate" in written.read_text(encoding="utf-8")


def test_an_empty_report_still_produces_a_page():
    html = TimingReport().as_html()
    assert "No phases were recorded" in html


def test_the_timing_report_setting_is_off_by_default():
    """A run writes nothing extra unless the user turned this on."""
    assert tunables.get("output.timing_report") is False


def test_the_dual_pdf_setting_is_off_by_default_and_offers_three_choices():
    spec = tunables.definition("output.dual_mode")
    assert spec is not None
    assert spec.default == ""
    assert [value for value, _label in spec.choices] == ["", "side", "alternate"]
    assert spec.group == "TEST_TOOLS"  # a stable key; the heading text comes from UIStrings
