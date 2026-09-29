"""Settings dialog for the runtime-adjustable parameters in `core/tunables.py`.

Applies immediately: the call sites read their value when they use it, so nothing here needs
the application restarted. A job already running keeps the values it started with, because
changing a batch size mid-request would be a way to corrupt that request rather than a feature.

The advanced section is separated and each of its entries carries a warning that says what
goes wrong, not merely that care is needed. Those are the settings where a bad value produces
quietly worse output instead of an obvious error - a font scale low enough to make text
unreadable still "fits", and a passthrough threshold set too high hides exactly the failure it
exists to catch.

Satırlar ve sayfalar `tweaks_editors` modülünde kurulur; bu dosya diyalogun kendisini ve
uygula / sıfırla / hazır ayar akışını tutar.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core import tunables
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.tweaks_editors import TEXT_WIDTH, build_section_page


def _editor_value(editor: QWidget) -> Any:
    """The editor's current value, whichever kind of editor it is."""
    if isinstance(editor, QComboBox):
        return editor.currentData()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, QLineEdit):
        return editor.text().strip()
    if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        return editor.value()
    return None


def _set_editor_value(editor: QWidget, value: Any) -> None:
    """Put a value back into an editor of any kind (used by Reset)."""
    if isinstance(editor, QComboBox):
        index = editor.findData(str(value or ""))
        editor.setCurrentIndex(index if index >= 0 else 0)
    elif isinstance(editor, QCheckBox):
        editor.setChecked(bool(value))
    elif isinstance(editor, QLineEdit):
        editor.setText(str(value or ""))
    elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        editor.setValue(float(value) if isinstance(editor, QDoubleSpinBox) else int(value))


class TweaksDialog(QDialog):
    #: "Show the welcome screen": it is dismissed for good on a first run.
    welcome_requested = Signal()
    """Edits tunables. `applied` fires whenever values change, so the app can refresh."""

    applied = Signal()

    def __init__(self, parent: QWidget | None = None, document_path: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.TWEAKS_TITLE)
        self.setMinimumWidth(620)
        # Without this the dialog opens as wide as its longest unwrapped text - the profile hint and
        # the advanced banner ran to 1300px on a 1366px screen, which is wider than the app itself.
        self.resize(760, 620)
        self._editors: dict[str, QWidget] = {}
        # The job's input, so the glossary editor can offer terms the document repeats. Empty when
        # the dialog is opened outside a job - the suggestion button stays off.
        self._document_path = document_path
        self._init_ui()

    def _init_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_section(tunables.BASIC), UIStrings.TWEAKS_TAB_BASIC)
        tabs.addTab(self._build_section(tunables.ADVANCED), UIStrings.TWEAKS_TAB_ADVANCED)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply_and_close)
        buttons.rejected.connect(self.reject)

        self._reset_btn = QPushButton(UIStrings.TWEAKS_RESET)
        self._reset_btn.clicked.connect(self._reset_all)
        # The welcome screen is dismissed for good on a first run, so this is the way back to it.
        self._welcome_btn = QPushButton(UIStrings.WELCOME_SHOW)
        self._welcome_btn.clicked.connect(self.welcome_requested.emit)

        bottom = QHBoxLayout()
        bottom.addWidget(self._reset_btn)
        bottom.addWidget(self._welcome_btn)
        bottom.addStretch()
        bottom.addWidget(buttons)

        self._footer = QLabel(UIStrings.TWEAKS_FOOTER)
        self._footer.setProperty("class", "muted")
        self._footer.setWordWrap(True)
        self._footer.setFixedWidth(TEXT_WIDTH)
        self._footer.setMinimumHeight(self._footer.heightForWidth(TEXT_WIDTH))

        # Hazır ayar: birkaç değeri birlikte değiştiren tek seçim. Değerler yine aynı doğrulanmış
        # yoldan yazılır, yani sonrasında tek tek düzenlenebilir ve dialogda görünür.
        self._profile = QComboBox()
        self._profile.addItem(UIStrings.PROFILE_CUSTOM, "")
        self._profile.addItem(UIStrings.PROFILE_DRAFT, "draft")
        self._profile.addItem(UIStrings.PROFILE_QUALITY, "quality")
        self._profile.setToolTip(UIStrings.PROFILE_HINT)
        self._sync_profile()
        self._profile.currentIndexChanged.connect(self._on_profile_changed)

        hint = QLabel(UIStrings.PROFILE_HINT)
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        hint.setFixedWidth(TEXT_WIDTH)
        hint.setMinimumHeight(hint.heightForWidth(TEXT_WIDTH))

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(UIStrings.PROFILE_LABEL))
        profile_row.addWidget(self._profile)
        profile_row.addWidget(hint, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(profile_row)
        layout.addWidget(tabs)
        layout.addWidget(self._footer)
        layout.addLayout(bottom)

    def _build_section(self, section: str) -> QWidget:
        # Satırlar ve katlanan gruplar `tweaks_editors`'te kurulur / Rows and groups are built there
        return build_section_page(section, self._editors, self._document_path)

    # -- actions -----------------------------------------------------------
    def apply_values(self) -> None:
        """Store every editor's value and persist. Out-of-range values are clamped."""
        for key, editor in self._editors.items():
            value = _editor_value(editor)
            if value is not None:
                tunables.set_value(key, value)
        tunables.save()
        self.applied.emit()

    def _sync_profile(self) -> None:
        """Point the combo at the profile the settings currently match (or "custom")."""
        from layoutkeep.core import profiles

        matched = profiles.current() or ""
        index = self._profile.findData(matched)
        self._profile.blockSignals(True)
        self._profile.setCurrentIndex(index if index >= 0 else 0)
        self._profile.blockSignals(False)

    def _on_profile_changed(self, _index: int) -> None:
        from layoutkeep.core import profiles

        chosen = self._profile.currentData() or ""
        if not chosen:
            return
        try:
            profiles.apply(chosen)
        except ValueError as error:
            self._footer.setText(str(error))
            return
        # The widgets show the values the dialog will save: a profile that moved them behind the
        # dialog's back would be overwritten by the next OK press.
        for key, editor in self._editors.items():
            _set_editor_value(editor, tunables.get(key))
        self.applied.emit()

    def _apply_and_close(self) -> None:
        self.apply_values()
        self.accept()

    def _reset_all(self) -> None:
        tunables.reset_all()
        tunables.save()
        for key, editor in self._editors.items():
            _set_editor_value(editor, tunables.get(key))
        self.applied.emit()
