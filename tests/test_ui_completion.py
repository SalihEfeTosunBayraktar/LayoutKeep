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


def test_the_box_flags_are_told_apart_from_the_text_ones(qtbot):
    """A flag whose cause is the box is a layout problem, and the screen must say so.

    Measured on the book: most flags are boxes `room_below` crushed to 6pt, where nothing fits at
    any length - a user reading only "N segments need review" would try rephrasing, which cannot
    help. The count is what tells the two apart.
    """
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("tr")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(segments_flagged=37, flagged_box_crushed=29))

    text = widget._stats_label.text()
    assert "37" in text
    assert "29" in text, text


def test_a_run_without_box_flags_does_not_mention_them(qtbot):
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("tr")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(segments_flagged=5, flagged_box_crushed=0))

    assert "5" in widget._stats_label.text()
    assert "kutu kısaltmasından" not in widget._stats_label.text()


def test_without_stats_the_block_stays_hidden(qtbot):
    """A failure path must not leave an empty labelled section behind."""
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(None)

    assert widget._stats_label.text() == ""


def test_what_verification_found_is_reported_by_kind(qtbot):
    """The application checks what it wrote (layoutkeep/verify.py). A loss it could not mend is
    flagged in the review queue; the completion screen has to say so, and say what kind."""
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("en")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(verify_repaired=3, verify_remaining={"L2": 2, "L7": 1}))

    text = widget._stats_label.text()
    assert "3 segments mended" in text
    assert "3 losses flagged" in text
    assert "left untranslated" in text and "drawn over other text" in text


def test_a_verified_clean_output_says_so(qtbot):
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("en")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(verify_repaired=0, verify_remaining={}))
    assert "no losses found" in widget._stats_label.text()

    widget.set_stats(_stats())  # a job that was not verified says nothing about it
    assert "Verification" not in widget._stats_label.text()


def test_the_glossary_check_is_reported(qtbot):
    """The terms the run was handed are checked in the output; the screen says how many were kept.

    A user reading only "N segments need review" cannot tell a term the model ignored from a
    paragraph that would not fit, and the two need different answers.
    """
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("en")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(glossary_checked=12, glossary_honoured=9))

    text = widget._stats_label.text()
    assert "9/12" in text, text
    assert "Glossary" in text, text


def test_a_run_without_a_glossary_says_nothing_about_terms(qtbot):
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("en")
    widget = CompletionWidget()
    qtbot.addWidget(widget)

    widget.set_stats(_stats(glossary_checked=0, glossary_honoured=0))

    assert "Glossary" not in widget._stats_label.text()
