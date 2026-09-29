"""The help screen: every section has something to say, and the criteria are the real ones.

A help screen is the easiest place in an application to write something that was true once. These
tests keep two promises: no section renders empty in a shipped language, and the criteria list is
generated from `verify.LABELS` rather than typed out a second time.
"""

from __future__ import annotations

import pytest

from layoutkeep.ui import help_text
from layoutkeep.ui.strings import UIStrings
from layoutkeep.verify import LABELS, LOSS_KINDS


@pytest.mark.parametrize("language", ["tr", "en"])
def test_every_section_has_a_title_and_a_body(qtbot, language):
    for key in help_text.SECTIONS:
        copy = help_text.text(language, key)
        assert copy["title"].strip(), f"{key} has no title in {language}"
        assert len(copy["body"].strip()) > 80, f"{key} says too little in {language}"


def test_the_criteria_section_is_built_from_the_checker(qtbot):
    from layoutkeep.ui.help_dialog import criteria_body

    body = criteria_body("en")

    for kind in LOSS_KINDS:
        assert kind in body, f"{kind} is missing from the help screen"
        assert LABELS[kind] in body, f"{kind}'s label is missing"


def test_the_dialog_lists_every_section_and_follows_the_language(qtbot):
    from layoutkeep.ui.help_dialog import HelpDialog

    UIStrings.set_language("tr")
    dialog = HelpDialog()
    qtbot.addWidget(dialog)

    assert dialog._list.count() == len(help_text.SECTIONS)
    assert dialog._list.item(0).text() == help_text.text("tr", help_text.SECTIONS[0])["title"]

    dialog._list.setCurrentRow(len(help_text.SECTIONS) - 1)
    shown = dialog._body.toPlainText()

    UIStrings.set_language("en")
    dialog.retranslate_ui()

    assert dialog._list.item(0).text() == help_text.text("en", help_text.SECTIONS[0])["title"]
    assert dialog._body.toPlainText() != shown, "the body did not follow the language"
    UIStrings.set_language("en")


def test_the_header_offers_help(qtbot):
    from layoutkeep.ui import header as header_module

    header = header_module.HeaderBar()
    qtbot.addWidget(header)
    seen: list[str] = []
    header.help_requested.connect(lambda: seen.append("asked"))

    header._help_btn.click()

    assert seen == ["asked"]


def test_the_window_opens_the_help_screen(qtbot, monkeypatch):
    from layoutkeep.ui import help_dialog
    from layoutkeep.ui.main_window import MainWindow

    opened: list[object] = []
    monkeypatch.setattr(help_dialog, "show_help", lambda parent=None: opened.append(parent))

    window = MainWindow()
    qtbot.addWidget(window)

    window.show_help()

    assert opened == [window]
