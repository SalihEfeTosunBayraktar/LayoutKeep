"""The floating bar and the window take turns.

Two bugs came out of one screenshot of a running job: the bar and the window's own progress screen
were on screen at the same time, and minimising the window took the bar down with it - the bar
being a Qt *owned* window, which Windows minimises together with its owner. These tests hold both
halves of the fix: the bar has no parent (so the window cannot drag it down), and only one of the
two is visible at a time.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from layoutkeep.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_the_bar_is_not_a_child_of_the_window(window: MainWindow) -> None:
    """A parent would make it an owned window, and Windows hides those with their owner."""
    assert window._floating is not None
    assert window._floating.parent() is None
    assert window._floating.isWindow()


def test_a_visible_window_keeps_the_bar_hidden(window: MainWindow) -> None:
    window.show()
    QApplication.processEvents()
    window._sync_bar_visibility()
    assert not window._floating.isVisible()


def test_the_bar_appears_when_the_window_is_out_of_the_way(window: MainWindow) -> None:
    window.show()
    QApplication.processEvents()
    window.hide()
    QApplication.processEvents()
    assert window._floating.isVisible()


def test_restoring_the_window_puts_the_bar_away_again(window: MainWindow) -> None:
    window.show()
    QApplication.processEvents()
    window.hide()
    QApplication.processEvents()
    window.show()
    QApplication.processEvents()
    assert not window._floating.isVisible()


def test_closing_the_window_takes_the_bar_with_it(window: MainWindow) -> None:
    """Explicitly: a parentless top-level widget that outlives its window crashes the next theme
    change, which is why this is a `deleteLater()` and not just a `close()`."""
    window.show()
    QApplication.processEvents()
    window.close()
    assert window._floating is None


def test_the_run_hands_over_to_the_bar(window: MainWindow) -> None:
    """The way back: once folded or closed, nothing used to bring the bar back."""
    window.show()
    QApplication.processEvents()
    window._worker = object()  # only "a run is going" is read here
    try:
        window._switch_to_bar()
        QApplication.processEvents()
        assert not window.isVisible()
        assert window._floating.isVisible()
    finally:
        window._worker = None


def test_the_header_carries_no_compact_bar_button(window: MainWindow) -> None:
    """Removed on request: the button sat in the header disabled until a run started.

    A control that is visible and cannot be pressed reads as a bug. The floating bar itself stays -
    it is still what a long run hands over to - but the header no longer offers a dead button for
    it, so this pins the removal rather than the old enable/disable dance.
    """
    header = window._header
    assert not hasattr(header, "_bar_btn")
    assert not hasattr(header, "set_bar_available")
    assert header.bar_requested is not None  # the window's own route to the bar still exists
