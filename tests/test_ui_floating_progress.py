"""The always-on-top summary bar: what it says, and what it turns into.

The bar exists so a long run can be followed while the application window is out of the way,
so these tests cover the three things a user reads off it - which document, which phase, how
far - and the two states it ends in (green finish with the way out, or a failure).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from layoutkeep.ui.floating_progress import FloatingProgress
from layoutkeep.ui.progress import format_phase
from layoutkeep.ui.strings import UIStrings


@pytest.fixture
def ui_language():
    """Set the interface language for one test and put it back afterwards.

    The language is global state: a test that leaves it on Turkish makes the next module's
    assertions fail, which is exactly the kind of order-dependent breakage this suite has
    been bitten by before.
    """
    previous = UIStrings.get_language()

    def select(language: str) -> None:
        UIStrings.set_language(language)

    yield select
    UIStrings.set_language(previous)


def test_phase_keys_become_readable_text(ui_language):
    """The worker sends machine names; the bar must not show them verbatim."""
    ui_language("en")

    assert format_phase("writing output") == UIStrings.STATUS_WRITING
    assert format_phase("verifying output") == UIStrings.STATUS_VERIFYING
    # Anything already written for a person is passed through untouched.
    assert format_phase("recovered 3 untranslated segments") == "recovered 3 untranslated segments"


def test_bar_shows_document_phase_counters_and_percent(qtbot, ui_language):
    ui_language("tr")
    bar = FloatingProgress()
    qtbot.addWidget(bar)

    bar.start_job("Introductory_Statistics.pdf", 44)
    bar.set_phase("translating")
    bar.set_progress(10, 44)

    assert "Introductory_Statistics.pdf" in bar._title.text()
    assert UIStrings.STATUS_TRANSLATING in bar._detail.text()
    assert UIStrings.FLOAT_SEGMENTS.format(done=10, total=44) in bar._detail.text()
    assert bar._percent.text() == "23%"
    assert (bar._bar.value(), bar._bar.maximum()) == (10, 44)


def test_a_finished_run_turns_the_bar_into_the_way_out(qtbot):
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.start_job("book.pdf", 4)
    bar.set_progress(4, 4)

    bar.finish("C:/tmp/book.tr.pdf")

    assert bar._percent.text() == "100%"
    assert bar._output_button.isVisibleTo(bar)
    assert bar._new_button.isVisibleTo(bar)
    assert not bar._pause_button.isVisibleTo(bar)
    assert bar.output_path() == "C:/tmp/book.tr.pdf"


def test_a_failed_run_says_so_and_still_offers_the_window(qtbot):
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.start_job("book.pdf", 4)

    bar.fail("RuntimeError: Context size has been exceeded\nsecond line")

    assert UIStrings.FLOAT_FAILED in bar._detail.text()
    assert "Context size has been exceeded" in bar._detail.text()
    assert "\n" not in bar._detail.text()  # a traceback must not stretch the bar
    assert bar._restore_button.isVisibleTo(bar)


def test_it_floats_above_other_windows_without_a_taskbar_entry():
    bar = FloatingProgress()

    assert bar.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert bar.windowFlags() & Qt.WindowType.Tool


def test_the_pause_button_announces_the_state_it_switched_to(qtbot):
    bar = FloatingProgress()
    qtbot.addWidget(bar)

    with qtbot.waitSignal(bar.pause_toggled):
        bar._pause_button.click()

    assert bar.is_paused()
    assert bar._pause_button.text() == UIStrings.FLOAT_RESUME


def test_folding_hides_the_details_but_keeps_the_percentage_and_a_way_back(qtbot):
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.start_job("book.pdf", 10)

    bar.toggle_folded()

    assert bar.is_folded()
    assert not bar._title.isVisibleTo(bar)
    assert not bar._detail.isVisibleTo(bar)
    assert not bar._bar.isVisibleTo(bar)
    assert not bar._restore_button.isVisibleTo(bar)
    assert bar._percent.isVisibleTo(bar)
    assert bar._fold_button.isVisibleTo(bar)

    bar.toggle_folded()

    assert not bar.is_folded()
    assert bar._detail.isVisibleTo(bar)
    assert bar._restore_button.isVisibleTo(bar)


def test_a_finished_run_unfolds_itself(qtbot):
    """Folding is for waiting; the end of a run must not stay hidden in a pill."""
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.start_job("book.pdf", 10)
    bar.toggle_folded()

    bar.finish("C:/tmp/book.tr.pdf")

    assert not bar.is_folded()
    assert bar._output_button.isVisibleTo(bar)


def test_dragging_the_card_moves_the_window(qtbot):
    """Frameless means there is no title bar: grabbing the card is the only way to move it."""
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    start = bar.pos()

    QTest.mousePress(bar._card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(bar._card, QPoint(120, 90))
    QTest.mouseRelease(bar._card, Qt.MouseButton.LeftButton, pos=QPoint(120, 90))

    assert bar.pos() != start
    assert bar.pos() == start + QPoint(100, 70)


def test_the_buttons_are_not_drag_handles(qtbot):
    """Dragging by a button would swallow the click the user meant to make."""
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    start = bar.pos()

    QTest.mousePress(bar._restore_button, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    QTest.mouseMove(bar._restore_button, QPoint(80, 60))
    QTest.mouseRelease(bar._restore_button, Qt.MouseButton.LeftButton, pos=QPoint(80, 60))

    assert bar.pos() == start


def test_a_drag_cannot_park_the_bar_out_of_reach(qtbot):
    """No title bar means no way back: a drag past the edge must leave a strip on screen."""
    bar = FloatingProgress()
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitExposed(bar)
    area = QApplication.primaryScreen().availableGeometry()

    QTest.mousePress(bar._card, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(bar._card, QPoint(-100_000, -100_000))
    QTest.mouseRelease(bar._card, Qt.MouseButton.LeftButton, pos=QPoint(-100_000, -100_000))

    assert bar.pos().x() + bar.width() >= area.left()
    assert bar.pos().y() >= area.top()
    assert bar.pos().y() <= area.bottom()
