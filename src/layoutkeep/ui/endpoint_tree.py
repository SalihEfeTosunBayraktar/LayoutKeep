"""The endpoint list as a tree of folders, arranged by dragging.

Groups are not configured anywhere: they are made the way folders are made on a phone's home
screen, by dropping one endpoint onto another. Dropping onto an endpoint that is already in a
folder joins that folder, dropping between two rows reorders, and a folder left empty
disappears rather than lingering as an empty heading nobody asked for.

The tree is the source of truth for both order and grouping, so every drop is followed by
reading the whole tree back into a list of profiles - there is no second place holding the
same arrangement that could disagree with what is on screen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from layoutkeep.ui.provider_profile import ProviderProfile

#: Role the profile is stored under. A folder row carries None here, which is what tells the
#: two kinds of row apart everywhere else.
PROFILE_ROLE = Qt.ItemDataRole.UserRole

_NEW_GROUP_NAME = "Yeni Grup"


def _is_folder(item: QTreeWidgetItem | None) -> bool:
    return item is not None and item.data(0, PROFILE_ROLE) is None


class EndpointTree(QTreeWidget):
    """Folders and endpoints, rearranged by dragging."""

    #: Emitted after any drop or rename, with the arrangement now on screen.
    arrangement_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setIndentation(16)
        self.setMinimumHeight(150)
        self.itemChanged.connect(self._on_item_changed)

    # -- contents ----------------------------------------------------------
    def load(self, profiles: list[ProviderProfile], select_name: str | None = None) -> None:
        """Rebuild the tree from stored profiles, keeping folders in first-seen order."""
        self.blockSignals(True)
        self.clear()
        folders: dict[str, QTreeWidgetItem] = {}
        selected: QTreeWidgetItem | None = None

        for profile in profiles:
            item = QTreeWidgetItem([profile.name])
            item.setData(0, PROFILE_ROLE, profile)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            if profile.group:
                folder = folders.get(profile.group)
                if folder is None:
                    folder = self._make_folder(profile.group)
                    folders[profile.group] = folder
                    self.addTopLevelItem(folder)
                folder.addChild(item)
            else:
                self.addTopLevelItem(item)
            if profile.name == select_name:
                selected = item

        self.expandAll()
        self.blockSignals(False)
        if selected is not None:
            self.setCurrentItem(selected)
        elif self.topLevelItemCount():
            self.setCurrentItem(self._first_endpoint())

    def _make_folder(self, name: str) -> QTreeWidgetItem:
        folder = QTreeWidgetItem([name])
        # Selectable so it can be renamed and dropped onto, but it holds no profile - the
        # dialog's form has nothing to show for a folder.
        folder.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDropEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsEditable
        )
        font = folder.font(0)
        font.setBold(True)
        folder.setFont(0, font)
        return folder

    def _first_endpoint(self) -> QTreeWidgetItem | None:
        for item in self.iter_endpoints():
            return item
        return None

    def iter_endpoints(self):
        for index in range(self.topLevelItemCount()):
            top = self.topLevelItem(index)
            if _is_folder(top):
                for child_index in range(top.childCount()):
                    yield top.child(child_index)
            else:
                yield top

    def selected_profile(self) -> ProviderProfile | None:
        item = self.currentItem()
        return None if item is None else item.data(0, PROFILE_ROLE)

    def to_profiles(self) -> list[ProviderProfile]:
        """The arrangement on screen, as the list that gets stored."""
        from dataclasses import replace

        result: list[ProviderProfile] = []
        for index in range(self.topLevelItemCount()):
            top = self.topLevelItem(index)
            if _is_folder(top):
                group = top.text(0).strip()
                for child_index in range(top.childCount()):
                    profile = top.child(child_index).data(0, PROFILE_ROLE)
                    if profile is not None:
                        result.append(replace(profile, group=group))
            else:
                profile = top.data(0, PROFILE_ROLE)
                if profile is not None:
                    result.append(replace(profile, group=""))
        return result

    # -- dragging ----------------------------------------------------------
    def dropEvent(self, event) -> None:
        dragged = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        position = self.dropIndicatorPosition()
        on_item = position == QAbstractItemView.DropIndicatorPosition.OnItem

        if dragged is None:
            event.ignore()
            return

        if _is_folder(dragged) and on_item:
            # Folders do not nest: a group inside a group is a structure nobody asked for and
            # the setup screen's dropdown cannot show.
            event.ignore()
            return

        if on_item and not _is_folder(dragged) and target is not None and target is not dragged:
            self._drop_onto(dragged, target)
            event.accept()
            self._announce()
            return

        super().dropEvent(event)
        for item in self.iter_endpoints():
            item.setHidden(False)
        self._prune_empty_folders()
        self._announce()

    def _drop_onto(self, dragged: QTreeWidgetItem, target: QTreeWidgetItem) -> None:
        # Bir uc noktayi digerinin ustune birakmak grup olusturur / Dropping one onto another
        # makes a group of the two, the way folders are made on a phone.
        self._detach(dragged)
        if _is_folder(target):
            target.addChild(dragged)
            target.setExpanded(True)
        elif target.parent() is not None:
            folder = target.parent()
            folder.insertChild(folder.indexOfChild(target) + 1, dragged)
            folder.setExpanded(True)
        else:
            index = self.indexOfTopLevelItem(target)
            self.takeTopLevelItem(index)
            folder = self._make_folder(self._unique_group_name())
            folder.addChild(target)
            folder.addChild(dragged)
            self.insertTopLevelItem(index, folder)
            folder.setExpanded(True)
        # Qt hides the row it is dragging and un-hides it when it completes the move itself.
        # This method does the move instead, so the row stayed hidden and the endpoint looked
        # like it had vanished into the group until the dialog was reopened.
        dragged.setHidden(False)
        self._prune_empty_folders()
        self.setCurrentItem(dragged)

    def _detach(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent is not None:
            parent.takeChild(parent.indexOfChild(item))
        else:
            self.takeTopLevelItem(self.indexOfTopLevelItem(item))

    def _unique_group_name(self) -> str:
        existing = {
            self.topLevelItem(i).text(0)
            for i in range(self.topLevelItemCount())
            if _is_folder(self.topLevelItem(i))
        }
        if _NEW_GROUP_NAME not in existing:
            return _NEW_GROUP_NAME
        counter = 2
        while f"{_NEW_GROUP_NAME} {counter}" in existing:
            counter += 1
        return f"{_NEW_GROUP_NAME} {counter}"

    def _prune_empty_folders(self) -> None:
        # Bos kalan grup kendiliginden kalkar / An emptied folder goes away by itself
        for index in reversed(range(self.topLevelItemCount())):
            item = self.topLevelItem(index)
            if _is_folder(item) and item.childCount() == 0:
                self.takeTopLevelItem(index)

    # -- edits -------------------------------------------------------------
    def ungroup(self, item: QTreeWidgetItem) -> None:
        """Take one endpoint out of its folder, or empty a folder entirely."""
        if _is_folder(item):
            index = self.indexOfTopLevelItem(item)
            children = item.takeChildren()
            self.takeTopLevelItem(index)
            for offset, child in enumerate(children):
                self.insertTopLevelItem(index + offset, child)
        elif item.parent() is not None:
            folder = item.parent()
            self._detach(item)
            self.insertTopLevelItem(self.indexOfTopLevelItem(folder) + 1, item)
        self._prune_empty_folders()
        self.setCurrentItem(item)
        self._announce()

    def rename_group(self, item: QTreeWidgetItem) -> None:
        if _is_folder(item):
            self.editItem(item, 0)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        # Grup adi degistiginde yeni duzeni bildirir / A renamed folder is a new arrangement
        if _is_folder(item):
            self._announce()

    def _announce(self) -> None:
        self.arrangement_changed.emit(self.to_profiles())
