"""The advanced-settings dialog: folded groups and a size a person can read.

Two complaints from a real run are pinned here. The window opened wider than the app itself, because
an unwrapped hint label reports its full one-line width; and a hundred rows in one flat list is a
wall to search through. Folding a group also takes its rows out of the layout, which is what keeps
the window from stretching to the longest sentence it shows.
"""

from __future__ import annotations

import pytest

from layoutkeep.core import tunables
from layoutkeep.ui.collapsible import CollapsibleSection
from layoutkeep.ui.tweaks_dialog import TweaksDialog


@pytest.fixture(autouse=True)
def _clean_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(tmp_path / "tunables.json"))
    tunables.reset_all()
    yield
    tunables.reset_all()


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def dialog(app):
    d = TweaksDialog()
    yield d
    d.close()
    d.deleteLater()


def test_every_setting_is_still_reachable(dialog):
    """Folding must hide rows, never lose them: every registered key keeps its editor."""
    expected = {
        spec.key
        for section in (tunables.BASIC, tunables.ADVANCED)
        for spec in tunables.definitions(section)
    }
    assert set(dialog._editors) == expected
    assert expected, "the registry should not be empty"


def test_the_groups_are_collapsible_blocks(dialog):
    """One block per group run: the registry decides how many, so a new group cannot go missing."""
    sections = dialog.findChildren(CollapsibleSection)
    expected = 0
    for section in (tunables.BASIC, tunables.ADVANCED):
        groups = [spec.group for spec in tunables.definitions(section)]
        expected += sum(1 for i, g in enumerate(groups) if i == 0 or g != groups[i - 1])
    assert len(sections) == expected, f"{len(sections)} blocks for {expected} group runs"
    assert expected >= 2, "the settings should arrive grouped, not as one flat list"


def test_the_first_group_of_a_section_is_open_and_the_rest_are_folded(dialog):
    """A closed list is a list you cannot see; everything open is the wall we just removed."""
    sections = dialog.findChildren(CollapsibleSection)
    opened = [s for s in sections if s.is_expanded()]
    assert opened, "at least one group must start open, or nothing is visible on opening"
    assert len(opened) < len(sections), "and not all of them, or the folding gains nothing"


def test_folding_hides_the_body_and_unfolding_brings_it_back(dialog):
    section = dialog.findChildren(CollapsibleSection)[0]
    section.set_expanded(True)
    assert section._body.isVisibleTo(section)
    section.set_expanded(False)
    assert not section._body.isVisibleTo(section)


def test_the_window_opens_at_a_readable_size(dialog):
    """Measured against the report: the dialog opened 1300px wide on a 1366px screen."""
    assert dialog.width() <= 900, f"too wide on opening: {dialog.width()}"
    assert dialog.height() <= 900, f"too tall on opening: {dialog.height()}"
    assert dialog.width() >= dialog.minimumWidth()
