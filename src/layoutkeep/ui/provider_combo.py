"""The setup screen's provider picker, showing groups as folders that open and close.

A flat dropdown with headings was readable while there were three endpoints and unreadable at
a dozen: every entry was on screen whether or not the group it belonged to was of any interest
right now. A tree lets a group be collapsed, and remembers which ones were - the arrangement
is the user's, and reopening the list should not undo it.

A folder is not a provider, so it cannot be selected; clicking it opens or closes it instead.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QTreeView

from layoutkeep.ui.provider_profile import ProviderProfile
from layoutkeep.ui.settings import app_settings

_COLLAPSED_KEY = "provider_groups_collapsed"


class ProviderComboBox(QComboBox):
    """Groups as folders, endpoints as their children."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tree = QTreeView(self)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setItemsExpandable(True)
        self._tree.setAllColumnsShowFocus(True)
        self.setView(self._tree)
        # One model for the life of the box, refilled in place. Replacing it on every populate
        # left the editable combo's completer pointing at a model nobody owned any more, and
        # the process died of heap corruption inside Qt's event loop several tests later.
        self._model = QStandardItemModel(self)
        self.setModel(self._model)

        # Editable with a read-only line edit is the only way the box can show a name that
        # lives inside a folder: a read-only combo refuses any text that is not a top row.
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setCursor(Qt.CursorShape.ArrowCursor)
        # Nothing to complete: the field is read-only and the list is a tree.
        self.setCompleter(None)
        # An editable combo opens its list from the arrow only, and its text field swallowed
        # the click, so clicking the box did nothing whatsoever. The field lets the mouse
        # through instead and the box handles the click itself.
        #
        # An event filter did this first and cost a crash: queued events reach a filter after
        # the widget that installed it has been destroyed, and the process died of an access
        # violation inside Qt's event loop, several tests after the one that made the widget.
        self.lineEdit().setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._chosen: str = ""

        self._tree.expanded.connect(lambda index: self._remember(index, expanded=True))
        self._tree.collapsed.connect(lambda index: self._remember(index, expanded=False))
        self._tree.clicked.connect(self._on_clicked)
        # Enter on a highlighted row, and the arrow keys that move the highlight: choosing
        # without the mouse has to end up in the same place as clicking.
        self._tree.activated.connect(self._on_clicked)
        self.currentIndexChanged.connect(self._on_index_changed)

    def mousePressEvent(self, event) -> None:
        # Anywhere on the box opens the list, which is what a dropdown does.
        if self.view().isVisible():
            self.hidePopup()
        else:
            self.showPopup()
        event.accept()

    def _on_index_changed(self, index: int) -> None:
        model = self.model()
        if index < 0 or index >= model.rowCount():
            return
        item = model.item(index)
        profile = item.data(Qt.ItemDataRole.UserRole)
        if profile is not None:
            self.select_profile(item.text())

    def _on_clicked(self, index) -> None:
        # Klasore tiklamak acar/kapatir, uc noktaya tiklamak secer / Folder toggles, endpoint
        # selects. Qt would otherwise treat a child's row number as a top-level row and choose
        # a different endpoint entirely.
        item = self.model().itemFromIndex(index)
        if item is None:
            return
        if item.data(Qt.ItemDataRole.UserRole) is None:
            self._tree.setExpanded(index, not self._tree.isExpanded(index))
            return
        self.select_profile(item.text())
        self.hidePopup()

    # -- contents ----------------------------------------------------------
    def populate(self, profiles: list[ProviderProfile], active_name: str = "") -> None:
        """Fill the list, folders first-seen order, and select `active_name` if it is there."""
        model = self._model
        model.clear()
        folders: dict[str, QStandardItem] = {}
        collapsed = self._collapsed_groups()
        selected: QStandardItem | None = None

        for profile in profiles:
            entry = QStandardItem(profile.name)
            entry.setData(profile, Qt.ItemDataRole.UserRole)
            entry.setEditable(False)
            if profile.group:
                folder = folders.get(profile.group)
                if folder is None:
                    folder = QStandardItem(profile.group)
                    folder.setEditable(False)
                    # A folder is a heading, not a choice: without this a job could start with
                    # a group name where a provider should be.
                    folder.setSelectable(False)
                    font = folder.font()
                    font.setBold(True)
                    folder.setFont(font)
                    folders[profile.group] = folder
                    model.appendRow(folder)
                folder.appendRow(entry)
            else:
                model.appendRow(entry)
            if profile.name == active_name:
                selected = entry

        for name, folder in folders.items():
            self._tree.setExpanded(folder.index(), name not in collapsed)

        if selected is not None:
            self.select_profile(selected.text())
        else:
            self._select_first_endpoint(model)

    def _select_first_endpoint(self, model: QStandardItemModel) -> None:
        for row in range(model.rowCount()):
            item = model.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self.select_profile(item.text())
                return
            if item.rowCount():
                self.select_profile(item.child(0).text())
                return
        self._chosen = ""
        self.lineEdit().setText("")

    # -- selection ---------------------------------------------------------
    def current_profile(self) -> ProviderProfile | None:
        """The chosen endpoint, or None while nothing is chosen."""
        wanted = self._chosen or self.currentText().strip()
        for profile in self.profiles():
            if profile.name == wanted:
                return profile
        return None

    def profiles(self) -> list[ProviderProfile]:
        model = self.model()
        found: list[ProviderProfile] = []
        for row in range(model.rowCount()):
            item = model.item(row)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data is not None:
                found.append(data)
            for child_row in range(item.rowCount()):
                child = item.child(child_row).data(Qt.ItemDataRole.UserRole)
                if child is not None:
                    found.append(child)
        return found

    def select_profile(self, name: str) -> None:
        """Choose an endpoint by name, wherever in the tree it sits."""
        self._chosen = name
        self.lineEdit().setText(name)

    # -- open/closed state -------------------------------------------------
    def _collapsed_groups(self) -> set[str]:
        stored = app_settings().value(_COLLAPSED_KEY, [])
        if isinstance(stored, str):
            stored = [stored] if stored else []
        return set(stored or [])

    def _remember(self, index, *, expanded: bool) -> None:
        item = self.model().itemFromIndex(index)
        if item is None or item.parent() is not None:
            return
        collapsed = self._collapsed_groups()
        collapsed.discard(item.text()) if expanded else collapsed.add(item.text())
        app_settings().setValue(_COLLAPSED_KEY, sorted(collapsed))
