"""Widget tests for the completion screen (step 3: open/folder/new translation).

The review editor was removed - step 3 is now a simple finished screen with three
actions: open the produced file, show it in a folder, or start another job.
"""

from __future__ import annotations

import pytest

from layoutkeep.ui.completion import CompletionWidget, format_duration


def test_initial_state_disables_actions(qtbot):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    assert not widget._open_btn.isEnabled()
    assert not widget._folder_btn.isEnabled()
    assert widget._output_label.text() == ""


def test_existing_output_enables_open_and_folder(qtbot, tmp_path):
    widget = CompletionWidget()
    qtbot.addWidget(widget)
    out = tmp_path / "cikti.pdf"
    out.write_bytes(b"%PDF-1.4 fake")

    widget.set_output_path(str(out))

    assert widget._open_btn.isEnabled()
    assert widget._folder_btn.isEnabled()
    assert out.name in widget._output_label.text()


def test_missing_output_disables_actions(qtbot, tmp_path):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_output_path(str(tmp_path / "never_written.pdf"))

    assert not widget._open_btn.isEnabled()
    assert not widget._folder_btn.isEnabled()
    assert widget._output_label.text() == ""


def test_empty_path_is_treated_as_missing(qtbot):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_output_path("")
    widget.set_output_path(None)

    assert not widget._open_btn.isEnabled()
    assert not widget._folder_btn.isEnabled()


def test_new_translation_button_emits_signal(qtbot):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.back_to_setup_requested, timeout=1000):
        widget._new_btn.click()


# ---------------------------------------------------------------------------
# Mockup 10: what the run actually did
#
# The screen used to show only the output path, so a job that flagged half its
# segments looked exactly like a clean one.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00"), (18, "00:18"), (138, "02:18"), (3661, "01:01:01"), (-5, "00:00")],
)
def test_duration_is_readable(seconds, expected):
    assert format_duration(seconds) == expected


def _stats(**overrides):
    base = {
        "segments_total": 412,
        "segments_done": 412,
        "segments_flagged": 0,
        "chars": 35000,
        "elapsed_s": 138.0,
        "chars_per_second": 172.0,
        "clean_ratio": 0.994,
    }
    base.update(overrides)
    return base


def test_the_figures_from_the_mockup_are_shown(qtbot):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats())

    text = widget._stats_label.text()
    assert "412" in text
    assert "172" in text, "average speed missing"
    assert "99.4" in text, "layout fidelity missing"
    assert "02:18" in text, "total time missing"


def test_flagged_segments_are_reported(qtbot):
    """A run that flagged segments must not look like a clean one."""
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(segments_flagged=37, clean_ratio=0.910))

    assert "37" in widget._stats_label.text()


def test_a_clean_run_says_nothing_about_flags(qtbot):
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(segments_flagged=0))

    assert "0 segment" not in widget._stats_label.text()


def test_without_stats_the_block_stays_hidden(qtbot):
    """A failure path must not leave an empty labelled section behind."""
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(None)

    assert widget._stats_label.text() == ""
