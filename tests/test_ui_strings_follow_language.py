"""Tests that a label built once still follows the interface language afterwards.

WHY THIS EXISTS: driving the built exe in Turkish showed an *English* hint sitting in the setup
card ("A second PDF is written beside the translated file...") next to Turkish labels, and the help
dialog's button read "Close". Both had the same cause: `JobSetupWidget` reads `UIStrings.DUAL_HINT`
and `UIStrings.RANGE_HINT` once in `__init__` and `retranslate_ui()` refreshed every other label but
not those two, while `QDialogButtonBox` takes its text from Qt's own catalog, which is not
installed. Neither showed up in the suite, because a test that builds a widget and never switches
the language cannot see a label that only updates on a switch.
"""

from __future__ import annotations

from layoutkeep.ui.main_window import MainWindow
from layoutkeep.ui.strings import UIStrings


def test_job_setup_hints_follow_a_language_switch(qtbot) -> None:
    # The window builds its widgets in whatever language the settings hold, so the switch is made
    # *after* construction - the same order the defect was seen in.
    window = MainWindow()
    qtbot.addWidget(window)
    UIStrings.set_language("tr")
    window._setup.retranslate_ui()
    turkish_hint = window._setup._range_hint.text()
    assert turkish_hint == UIStrings.RANGE_HINT
    assert window._setup._range_input.placeholderText() == UIStrings.RANGE_PLACEHOLDER

    UIStrings.set_language("en")
    window._setup.retranslate_ui()
    english_hint = window._setup._range_hint.text()
    assert english_hint == UIStrings.RANGE_HINT
    # The point of the test: the text moved with the language instead of staying where it started.
    assert english_hint != turkish_hint

    UIStrings.set_language("tr")


def test_every_language_defines_the_close_button() -> None:
    """The help dialog no longer uses Qt's own button text, so the key has to exist everywhere."""
    for language in ("tr", "en", "de"):
        UIStrings.set_language(language)
        assert UIStrings.CLOSE_BTN.strip(), language
    UIStrings.set_language("tr")
