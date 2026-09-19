"""The welcome screen: shown once, walkable, translatable, and remembered.

The screen is dismissed for good on a first run, so the tests that matter are the ones about that
promise (shown when it has never been seen, not shown afterwards), about the page walk, and about
the copy existing in every interface language - a missing translation here is the first thing a new
user would see.
"""

from __future__ import annotations

import pytest

from layoutkeep.ui import main_window, welcome_text
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.welcome import WelcomeDialog


@pytest.fixture(autouse=True)
def _restore_language():
    previous = UIStrings.get_language()
    UIStrings.set_language("tr")
    yield
    UIStrings.set_language(previous)


def test_every_page_has_copy_in_every_supported_language():
    for code, _label in UIStrings.SUPPORTED_LANGUAGES:
        for page in welcome_text.PAGES:
            assert welcome_text.text(code, page, "title"), f"{code}/{page} başlıksız"
            body = welcome_text.text(code, page, "lead") + welcome_text.text(code, page, "bullets")
            assert len(body) > 80, f"{code}/{page} metni çok kısa"


def test_the_walk_starts_at_the_first_page_and_ends_on_start(qtbot):
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)

    assert dialog._stack.currentWidget().property("welcome_page") == "hello"
    assert not dialog._back.isVisibleTo(dialog)
    assert dialog._next.isVisibleTo(dialog)
    assert dialog._skip.isVisibleTo(dialog)

    for _ in range(len(welcome_text.PAGES) - 1):
        dialog._advance()

    assert dialog._stack.currentWidget().property("welcome_page") == "done"
    assert dialog._skip.isVisibleTo(dialog) is False
    assert dialog._back.isVisibleTo(dialog)


def test_switching_language_retranslates_and_announces_it(qtbot):
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)

    with qtbot.waitSignal(dialog.language_changed) as caught:
        dialog._language.setCurrentIndex(1)  # English, per SUPPORTED_LANGUAGES order

    assert caught.args == ["en"]
    assert "Welcome" in dialog._heading.text()


def test_the_theme_button_announces_the_theme_it_switched_to(qtbot):
    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)
    before = dialog._theme.text()

    with qtbot.waitSignal(dialog.theme_changed) as caught:
        dialog._theme.click()

    assert caught.args == [True] or caught.args == [False]
    assert dialog._theme.text() != before


def test_finishing_remembers_that_it_was_seen(qtbot):
    from layoutkeep.ui.settings import app_settings

    dialog = WelcomeDialog()
    qtbot.addWidget(dialog)

    dialog._finish()

    assert app_settings().value("welcome_shown", False, type=bool) is True


def test_the_window_asks_for_the_introduction_only_until_it_has_been_seen(qtbot, monkeypatch):
    """The promise is "once": a second start must not show it again."""
    from layoutkeep.ui.main_window import MainWindow
    from layoutkeep.ui.settings import app_settings

    app_settings().setValue("welcome_shown", False)
    window = MainWindow()
    qtbot.addWidget(window)
    shown: list[str] = []
    monkeypatch.setattr(window, "show_welcome", lambda: shown.append("shown"))
    # The session switch that keeps the suite from opening the modal screen would also keep this
    # test from exercising the once-only rule, so the wanted path is put back for these calls.
    monkeypatch.setattr(main_window, "_welcome_is_wanted", lambda: True)

    window._maybe_show_welcome()
    assert shown == ["shown"]

    app_settings().setValue("welcome_shown", True)
    window._maybe_show_welcome()
    assert shown == ["shown"]
