"""Endpoints are added, saved, grouped and ordered by hand.

A translation setup tends to accumulate endpoints - two local servers, a machine on the
network, a paid service - and the list was a flat dropdown in whatever order the profiles
happened to have been written. These tests pin the three things that changed: a group can be
given to an endpoint and shows as a heading, the order can be rearranged and sticks, and
saving an endpoint does not close the dialog on the way.
"""

from __future__ import annotations

import pytest

from layoutkeep.ui import keyring_store
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.provider_profile import ProviderProfile, ProviderProfileStore
from layoutkeep.ui.provider_settings import ProviderSettingsDialog


@pytest.fixture
def fake_keyring(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(keyring_store, "set_api_key", lambda url, key: store.__setitem__(url, key))
    monkeypatch.setattr(keyring_store, "get_api_key", lambda url: store.get(url))
    monkeypatch.setattr(keyring_store, "delete_api_key", lambda url: store.pop(url, None))
    return store


@pytest.fixture
def three_endpoints() -> ProviderProfileStore:
    """A store holding two grouped endpoints and one loose one, in a known order.

    The settings are isolated per session, not per test, so a fixture that writes profiles and
    walks away leaves them for every test that runs afterwards - which is how this one first
    broke five unrelated tests that iterate the provider list. It puts the store back.
    """
    from layoutkeep.ui.settings import app_settings

    settings = app_settings()
    before = settings.value("provider_profiles_v1")
    before_active = settings.value("active_provider_profile")

    store = ProviderProfileStore()
    store.save_profiles(
        [
            ProviderProfile(name="LM Studio", kind="openai", base_url="http://a/v1", group="Yerel"),
            ProviderProfile(name="Ollama", kind="openai", base_url="http://b/v1", group="Yerel"),
            ProviderProfile(name="Kiralik GPU", kind="openai", base_url="http://c/v1"),
        ]
    )
    yield store

    for key, value in (
        ("provider_profiles_v1", before),
        ("active_provider_profile", before_active),
    ):
        if value is None:
            settings.remove(key)
        else:
            settings.setValue(key, value)


# -- the store -----------------------------------------------------------------------------


def test_the_arranged_order_is_what_is_stored(three_endpoints: ProviderProfileStore) -> None:
    three_endpoints.move_profile("Ollama", -1)

    assert [p.name for p in three_endpoints.list_profiles()][:2] == ["Ollama", "LM Studio"]


def test_moving_past_either_end_does_nothing(three_endpoints: ProviderProfileStore) -> None:
    """Wrapping around would make a repeated click jump the entry from top to bottom, which is
    hard to aim; stopping at the end is what a user expects from an up arrow."""
    before = [p.name for p in three_endpoints.list_profiles()]

    three_endpoints.move_profile(before[0], -1)
    three_endpoints.move_profile(before[-1], 1)

    assert [p.name for p in three_endpoints.list_profiles()] == before


def test_groups_are_listed_in_the_order_they_first_appear(
    three_endpoints: ProviderProfileStore,
) -> None:
    three_endpoints.upsert_profile(
        ProviderProfile(name="DeepL", kind="deepl", base_url="", group="Bulut")
    )

    assert three_endpoints.groups() == ["Yerel", "Bulut"]


def test_a_profile_saved_before_grouping_existed_reads_back_ungrouped() -> None:
    """Everything already stored was written without a group, and must still load."""
    import json

    from layoutkeep.ui.settings import app_settings

    settings = app_settings()
    before = settings.value("provider_profiles_v1")
    settings.setValue(
        "provider_profiles_v1",
        json.dumps([{"name": "Eski", "kind": "openai", "base_url": "http://x/v1", "model": ""}]),
    )
    try:
        stored = ProviderProfileStore().get_profile("Eski")
    finally:
        if before is None:
            settings.remove("provider_profiles_v1")
        else:
            settings.setValue("provider_profiles_v1", before)

    assert stored is not None
    assert stored.group == ""


# -- the settings dialog -------------------------------------------------------------------


def test_the_dialog_shows_endpoints_inside_their_folders(
    qtbot, fake_keyring, three_endpoints
) -> None:
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)

    tree = dialog._form.endpoint_list
    folder = tree.topLevelItem(0)

    assert folder.text(0) == "Yerel"
    assert [folder.child(i).text(0) for i in range(folder.childCount())] == [
        "LM Studio",
        "Ollama",
    ]
    # The loose one stays at the top level rather than being filed under something invented.
    assert tree.topLevelItem(1).text(0) == "Kiralik GPU"
    assert folder.isExpanded()


def test_saving_an_endpoint_keeps_the_dialog_open(qtbot, fake_keyring, three_endpoints) -> None:
    """Adding several endpoints in one visit is the normal case."""
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)

    closed: list[int] = []
    dialog.finished.connect(closed.append)

    dialog._form.new_profile_btn.click()
    dialog._form.profile_name.setText("Yeni Sunucu")
    dialog._form.group.setCurrentText("Bulut")
    dialog._form.base_url.setText("http://new/v1")
    dialog._form.save_btn.click()

    assert closed == [], "kaydetmek diyalogu kapatmamali"
    saved = three_endpoints.get_profile("Yeni Sunucu")
    assert saved is not None and saved.group == "Bulut"
    tree = dialog._form.endpoint_list
    folders = [
        tree.topLevelItem(i).text(0)
        for i in range(tree.topLevelItemCount())
        if tree.topLevelItem(i).childCount()
    ]
    assert "Bulut" in folders


def test_dropping_one_endpoint_onto_another_makes_a_group_of_them(
    qtbot, fake_keyring, three_endpoints
) -> None:
    """The gesture is the one that makes a folder on a phone's home screen, and it is the only
    way to make a group - there is nowhere else to declare one."""
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)
    tree = dialog._form.endpoint_list

    loose = tree.topLevelItem(1)  # Kiralik GPU, ungrouped
    other = tree.topLevelItem(0).child(0)  # LM Studio, inside "Yerel"
    tree.setCurrentItem(loose)
    tree._drop_onto(loose, other)
    tree._announce()

    stored = {p.name: p.group for p in three_endpoints.list_profiles()}
    assert stored["Kiralik GPU"] == "Yerel"


def test_a_group_emptied_by_dragging_disappears(qtbot, fake_keyring, three_endpoints) -> None:
    """An empty folder is a heading with nothing under it; leaving one behind would make the
    setup screen show a group the user has already dismantled."""
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)
    tree = dialog._form.endpoint_list

    folder = tree.topLevelItem(0)
    while folder.childCount():
        tree.ungroup(folder.child(0))

    # (the store also keeps a DeepL and a test entry present, so check the three by name)
    groups = {p.name: p.group for p in three_endpoints.list_profiles()}
    assert groups["LM Studio"] == groups["Ollama"] == groups["Kiralik GPU"] == ""
    assert all(
        tree.topLevelItem(i).childCount() == 0 for i in range(tree.topLevelItemCount())
    )


def test_renaming_a_group_renames_it_for_every_endpoint_in_it(
    qtbot, fake_keyring, three_endpoints
) -> None:
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)
    tree = dialog._form.endpoint_list

    tree.topLevelItem(0).setText(0, "Ev")

    groups = {p.name: p.group for p in three_endpoints.list_profiles()}
    assert groups["LM Studio"] == "Ev"
    assert groups["Ollama"] == "Ev"


# -- the setup screen ----------------------------------------------------------------------


def test_the_setup_screen_shows_the_same_folders_and_order(qtbot, three_endpoints) -> None:
    """The picker is a tree, so a group can be folded away - a flat list of every endpoint was
    readable at three and unreadable at a dozen."""
    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    combo = widget._provider_profile_combo
    model = combo.model()
    folder = model.item(0)

    assert folder.text() == "Yerel"
    assert [folder.child(i).text() for i in range(folder.rowCount())] == ["LM Studio", "Ollama"]
    assert model.item(1).text() == "Kiralik GPU"

    # A folder is a heading, not a provider: a job must never start with a group name where a
    # provider should be.
    assert not folder.isSelectable()
    assert combo.current_profile() is not None


def test_a_folded_group_stays_folded_next_time(qtbot, three_endpoints) -> None:
    """Folding is the point of the tree; reopening the screen and finding it undone would make
    the gesture pointless."""
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    combo = widget._provider_profile_combo

    combo._tree.collapse(combo.model().item(0).index())

    later = JobSetupWidget()
    qtbot.addWidget(later)
    later_combo = later._provider_profile_combo
    assert not later_combo._tree.isExpanded(later_combo.model().item(0).index())


def test_choosing_an_endpoint_inside_a_folder_selects_that_endpoint(
    qtbot, three_endpoints
) -> None:
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    combo = widget._provider_profile_combo

    combo.select_profile("Ollama")

    assert combo.current_profile().name == "Ollama"
    assert widget._provider_config.base_url == "http://b/v1"


def test_the_dragged_endpoint_is_still_visible_after_it_joins_a_group(
    qtbot, fake_keyring, three_endpoints
) -> None:
    """Qt hides the row it is dragging and un-hides it when it finishes the move itself. The
    grouping drop is handled by the tree instead, so nothing un-hid it and the endpoint looked
    like it had vanished into the folder until the dialog was reopened."""
    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)
    tree = dialog._form.endpoint_list

    loose = tree.topLevelItem(1)
    target = tree.topLevelItem(0).child(0)
    tree.setCurrentItem(loose)
    loose.setHidden(True)  # what Qt does while the drag is in flight
    tree._drop_onto(loose, target)

    assert not loose.isHidden()


def test_clicking_the_provider_box_opens_the_list(qtbot, three_endpoints) -> None:
    """The box is editable so its text can show a name that lives inside a folder, and an
    editable combo opens its list from the arrow only - clicking the (read-only) text field
    did nothing at all, which reads as a broken control."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    combo = widget._provider_profile_combo

    # The text field lets the mouse through so the box itself sees the click.
    assert combo.lineEdit().testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    opened: list[bool] = []
    combo.showPopup = lambda: opened.append(True)  # type: ignore[method-assign]
    combo.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert opened == [True], "tiklamak listeyi acmali"


def test_the_right_click_menu_builds_and_its_actions_work(
    qtbot, fake_keyring, three_endpoints
) -> None:
    """It is the only way to delete or rename an endpoint, and in the packaged application it
    did not open at all: `addAction(text, callable)` has a sibling overload taking a receiver
    and a slot name, and a bound method of a QObject picks that one - Qt then looks for a slot
    that does not exist and raises. The crash log from a real run carried exactly that line."""
    from layoutkeep.ui.strings import UIStrings

    dialog = ProviderSettingsDialog(ProviderConfig(kind="openai"))
    qtbot.addWidget(dialog)
    tree = dialog._form.endpoint_list

    folder_menu = dialog.build_endpoint_menu(tree.topLevelItem(0))
    assert [action.text() for action in folder_menu.actions()] == [
        UIStrings.MENU_RENAME_GROUP,
        UIStrings.MENU_UNGROUP_ALL,
    ]

    endpoint = tree.topLevelItem(0).child(1)  # Ollama, inside a group
    endpoint_menu = dialog.build_endpoint_menu(endpoint)
    labels = [action.text() for action in endpoint_menu.actions() if action.text()]
    assert UIStrings.MENU_TEST_CONNECTION in labels
    assert UIStrings.MENU_LEAVE_GROUP in labels
    assert UIStrings.MENU_DELETE in labels

    # And triggering one does what it says, rather than raising on the way.
    delete = next(a for a in endpoint_menu.actions() if a.text() == UIStrings.MENU_DELETE)
    delete.trigger()

    assert three_endpoints.get_profile("Ollama") is None
