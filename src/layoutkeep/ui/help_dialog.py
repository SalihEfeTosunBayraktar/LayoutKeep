"""The help screen: what a setting does, what a flag means, where the outputs are.

WHY THIS EXISTS: the application explains itself in tooltips, which is right next to the control but
gone the moment the pointer moves, and in the welcome screen, which is read once. Neither answers
"what does this flag mean" or "why did the server say the model is missing" while the user is
looking at exactly that. The criteria list is generated from `verify.LABELS` rather than typed in,
so it cannot describe a checker other than the one that ships.

Both the welcome screen and this one keep their prose in a separate data module
(`welcome_text.py`, `help_text.py`); a screen that mixes behaviour with a page of Turkish and a page
of English is hard to change in either direction.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui import help_text
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager


def criteria_body(language: str) -> str:
    """The criteria list, built from the checker's own labels.

    A hand-written list in a help screen is a promise to update two places; this one is true by
    construction, and it is what tells a reader that `L10` is about figures rather than text.
    """
    from layoutkeep.verify import LABELS, LOSS_KINDS

    head = help_text.text(language, "criteria")["body"]
    losses = "\n".join(f"• {kind} — {LABELS[kind]}" for kind in LOSS_KINDS)
    return f"{head}\n\n{losses}"


class HelpDialog(QDialog):
    """A section list on the left, the chosen section on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.HELP_TITLE)
        self.resize(760, 560)
        self._sections = help_text.SECTIONS
        self._list = QListWidget()
        self._list.setFixedWidth(210)
        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        # Qt ships no translation catalog here, so a standard button stays English in a Turkish
        # window (seen by driving the built exe). The text comes from the same place as every
        # other label instead.
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(UIStrings.CLOSE_BTN)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        columns = QHBoxLayout()
        columns.addWidget(self._list)
        columns.addWidget(self._body, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(columns)
        layout.addWidget(buttons)

        self._list.currentRowChanged.connect(self._show_section)
        self.retranslate_ui()

    # -- presentation ------------------------------------------------------
    def apply_theme(self) -> None:
        """Re-read the palette; the dialog is opened from a themed window and must match it."""
        palette = ThemeManager.current_palette()
        self._body.setStyleSheet(f"QTextBrowser {{ color: {palette.text_primary}; }}")
        self._list.setStyleSheet(f"QListWidget {{ color: {palette.text_primary}; }}")

    def retranslate_ui(self) -> None:
        language = UIStrings.get_language()
        row = max(0, self._list.currentRow())
        self._list.blockSignals(True)
        self._list.clear()
        self._list.addItems([help_text.text(language, key)["title"] for key in self._sections])
        self._list.setCurrentRow(row)
        self._list.blockSignals(False)
        self._show_section(row)
        self.apply_theme()

    # -- content -----------------------------------------------------------
    def _show_section(self, row: int) -> None:
        if row < 0 or row >= len(self._sections):
            return
        key = self._sections[row]
        language = UIStrings.get_language()
        copy = help_text.text(language, key)
        body = criteria_body(language) if key == "criteria" else copy["body"]
        self._body.setHtml(
            f"<h2 style='margin-bottom:2px'>{copy['title']}</h2>"
            f"<div style='white-space:pre-wrap'>{_escaped(body)}</div>"
        )


def _escaped(text: str) -> str:
    """Escape for HTML, then turn blank lines into paragraph breaks."""
    escaped = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return escaped.replace("\n", "<br>")


def show_help(parent: QWidget | None = None) -> None:
    """Open the help screen modally; the caller owns nothing."""
    dialog = HelpDialog(parent)
    dialog.exec()


__all__ = ["HelpDialog", "criteria_body", "show_help"]
