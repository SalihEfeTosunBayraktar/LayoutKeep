"""Every widget the interface uses has a rule in the theme table.

This test exists because the same defect turned up five times in one week, always the same way:
a widget class with no entry in the stylesheet is painted by the desktop instead, so under a
light theme on a Windows machine set to dark mode it came out dark-on-dark. It cost an
unreadable error dialog (QMessageBox), a dark list inside a white dialog (QListWidget, then
QTreeView), an advanced settings page drawn in the wrong theme (QTabWidget, QScrollArea), value
boxes with no value visible at all (QSpinBox) and a dark context menu (QMenu).

Every one of those was found by a person looking at a screenshot. This finds the next one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from layoutkeep.ui.theme import ThemeManager

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "layoutkeep" / "ui"

#: Widget classes that paint their own background or text and therefore need a rule. A layout
#: or a non-visual helper does not; those are left out deliberately rather than by oversight.
PAINTS_ITSELF = frozenset(
    {
        "QCheckBox",
        "QComboBox",
        "QDialog",
        "QDoubleSpinBox",
        "QFrame",
        "QGroupBox",
        "QLabel",
        "QLineEdit",
        "QListWidget",
        "QMainWindow",
        "QMenu",
        "QMessageBox",
        "QPlainTextEdit",
        "QProgressBar",
        "QPushButton",
        "QScrollArea",
        "QSlider",
        "QSpinBox",
        "QStackedWidget",
        "QTabWidget",
        "QTextEdit",
        "QToolButton",
        "QTreeView",
        "QTreeWidget",
    }
)

#: A rule for the base class covers what derives from it, so these do not need their own.
COVERED_BY = {"QTreeWidget": "QTreeView", "QMessageBox": "QDialog"}


def _widgets_used() -> set[str]:
    used: set[str] = set()
    for module in UI_DIR.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        # Constructed (`QLabel(...)`) or subclassed (`class X(QTreeWidget)`).
        used |= set(re.findall(r"\b(Q[A-Z][A-Za-z]+)\s*\(", source))
    return used & PAINTS_ITSELF


def test_every_painted_widget_has_a_theme_rule() -> None:
    stylesheet = ThemeManager.get_stylesheet()

    missing = [
        widget
        for widget in sorted(_widgets_used())
        if widget not in stylesheet and COVERED_BY.get(widget, "") not in stylesheet
    ]

    assert not missing, (
        "tema tablosunda kurali olmayan bilesenler: "
        + ", ".join(missing)
        + " - kurali olmayan bir bilesen masaustu temasiyla boyanir ve acik temada okunmaz"
    )


def test_the_check_would_notice_a_missing_rule() -> None:
    """A guard that cannot fail is worse than no guard: pin that this one can."""
    stylesheet = ThemeManager.get_stylesheet()

    assert "QSpinBox" in stylesheet, "spin box rule went missing"
    assert "QNonexistentWidget" not in stylesheet
