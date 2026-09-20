"""Profiles: one choice that moves several tunables, and says honestly whether it still matches.

The two properties worth holding: applying a profile goes through the same validated path the
settings dialog uses (so a profile cannot put a value somewhere the dialog would refuse), and
`current()` reports the profile only while *every* value still matches - a user who changed one
value afterwards has left the profile, and claiming otherwise would be a small lie in the
interface.
"""

from __future__ import annotations

import pytest

from layoutkeep.core import profiles, tunables


@pytest.fixture(autouse=True)
def _restore_tunables():
    """Every test here writes tunables; the suite must not inherit them."""
    keys = [spec.key for spec in tunables.TUNABLES]
    before = {key: tunables.get(key) for key in keys}
    yield
    for key, value in before.items():
        tunables.set_value(key, value)


def test_the_repository_defaults_are_the_quality_profile() -> None:
    """A fresh install is the careful profile, not the fast one - the first run should be the
    one worth keeping."""
    for key, value in profiles.PROFILES["quality"].items():
        if tunables.get(key) != value:
            tunables.set_value(key, value)

    assert profiles.current() == "quality"


def test_applying_a_profile_sets_every_value() -> None:
    profiles.apply("draft")

    for key, value in profiles.PROFILES["draft"].items():
        assert tunables.get(key) == value, key
    assert profiles.current() == "draft"


def test_editing_one_value_leaves_the_profile() -> None:
    profiles.apply("draft")
    tunables.set_value("fit.min_scale", 0.83)

    assert profiles.current() is None


def test_an_unknown_profile_is_refused() -> None:
    with pytest.raises(ValueError):
        profiles.apply("turbo")


def test_a_profile_value_is_clamped_by_the_same_rules_as_the_dialog() -> None:
    """`set_value` clamps rather than raising; a profile that asked for an impossible value must
    end up at the same place the dialog would put it."""
    spec = tunables.definition("fit.min_scale")
    profiles.apply("draft")

    stored = tunables.get("fit.min_scale")
    assert spec.minimum <= stored <= spec.maximum


def test_the_draft_profile_is_faster_than_the_quality_one() -> None:
    """The point of the profile: more requests in flight and no extra model round-trips."""
    draft = profiles.PROFILES["draft"]
    quality = profiles.PROFILES["quality"]

    assert draft["translation.workers"] > quality["translation.workers"]
    assert draft["fit.shorten_below_scale"] < quality["fit.shorten_below_scale"]


def test_the_settings_dialog_applies_a_profile_and_shows_it(qtbot) -> None:
    """Through the dialog: pick a preset, the values move, and the editors show the new values
    (a profile that moved them behind the dialog's back would be overwritten by the next OK)."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from layoutkeep.ui.tweaks_dialog import TweaksDialog, _editor_value

    app = QApplication.instance() or QApplication([])
    dialog = TweaksDialog()
    qtbot.addWidget(dialog)

    dialog._profile.setCurrentIndex(dialog._profile.findData("draft"))
    app.processEvents()

    assert profiles.current() == "draft"
    workers_editor = dialog._editors["translation.workers"]
    assert _editor_value(workers_editor) == profiles.PROFILES["draft"]["translation.workers"]

    dialog._profile.setCurrentIndex(dialog._profile.findData("quality"))
    app.processEvents()

    assert profiles.current() == "quality"
    assert _editor_value(dialog._editors["fit.min_scale"]) == profiles.PROFILES["quality"]["fit.min_scale"]


def test_the_dialog_opens_on_custom_when_nothing_matches(qtbot) -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    app = QApplication.instance() or QApplication([])
    tunables.set_value("fit.min_scale", 0.83)
    dialog = TweaksDialog()
    qtbot.addWidget(dialog)

    assert dialog._profile.currentData() == "", "a hand-edited setting is not a profile"
