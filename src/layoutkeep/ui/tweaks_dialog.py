"""Settings dialog for the runtime-adjustable parameters in `core/tunables.py`.

Applies immediately: the call sites read their value when they use it, so nothing here needs
the application restarted. A job already running keeps the values it started with, because
changing a batch size mid-request would be a way to corrupt that request rather than a feature.

The advanced section is separated and each of its entries carries a warning that says what
goes wrong, not merely that care is needed. Those are the settings where a bad value produces
quietly worse output instead of an obvious error - a font scale low enough to make text
unreadable still "fits", and a passthrough threshold set too high hides exactly the failure it
exists to catch.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core import tunables
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

#: Width the label column is fixed to, for the same reason.
_LABEL_WIDTH = 210

#: Width the value column is fixed to. Word-wrapped help and warning text needs a known
#: width before it can report the height it will occupy.
_FIELD_WIDTH = 300


def _editor_for(spec: tunables.Tunable) -> QWidget:
    """Türüne uygun düzenleyici üretir / Builds the editor matching the tunable's type.

    Four kinds, not two: a switch (the translation memory) and a file path (the glossary) are
    settings the same way the numbers are, and they belong on the same page with the same help
    text - not in a second dialog the user has to find.
    """
    value = tunables.get(spec.key)
    if spec.kind == "bool":
        check = QCheckBox()
        check.setChecked(bool(value))
        return check
    if spec.kind == "str":
        line = QLineEdit(str(value or ""))
        line.setPlaceholderText("…")
        return line
    box: QSpinBox | QDoubleSpinBox
    if spec.kind == "int":
        box = QSpinBox()
        box.setRange(int(spec.minimum or 0), int(spec.maximum or 10_000))
    else:
        box = QDoubleSpinBox()
        box.setDecimals(2)
        box.setSingleStep(0.05)
        box.setRange(float(spec.minimum or 0.0), float(spec.maximum or 10_000.0))
    box.setValue(value)
    return box


def _editor_value(editor: QWidget) -> Any:
    """The editor's current value, whichever kind of editor it is."""
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, QLineEdit):
        return editor.text().strip()
    if isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        return editor.value()
    return None


def _set_editor_value(editor: QWidget, value: Any) -> None:
    """Put a value back into an editor of any kind (used by Reset)."""
    if isinstance(editor, QCheckBox):
        editor.setChecked(bool(value))
    elif isinstance(editor, QLineEdit):
        editor.setText(str(value or ""))
    elif isinstance(editor, (QSpinBox, QDoubleSpinBox)):
        editor.setValue(float(value) if isinstance(editor, QDoubleSpinBox) else int(value))


def _editor_holder(
    editor: QWidget, spec: tunables.Tunable, document_path: str = ""
) -> tuple[QWidget, QWidget]:
    """The editor, plus a "Browse" companion when the tunable is a path.

    Returns (holder, focus_widget): the holder goes into the form, the focus widget is what the
    caption's width is measured against.
    """
    if spec.kind != "str":
        return editor, editor
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    line = editor
    row.addWidget(line, 1)
    browse = QPushButton(UIStrings.TWEAKS_BROWSE)
    browse.setToolTip(UIStrings.TWEAKS_GLOSSARY_TIP)
    browse.clicked.connect(lambda: _pick_file(line))
    row.addWidget(browse, 0)
    if spec.key == "translation.glossary_path":
        # The file is a list of term pairs, not a line of JSON to type: the editor opens the same
        # file this field points at and writes it back.
        edit = QPushButton(UIStrings.GLOSSARY_EDIT)
        edit.setToolTip(UIStrings.GLOSSARY_TABLE_TIP)
        edit.clicked.connect(lambda: _edit_glossary(line, document_path))
        row.addWidget(edit, 0)
    return holder, line


def _edit_glossary(line: QLineEdit, document_path: str = "") -> None:
    """Open the glossary editor and keep the path field in step with what it saved."""
    from layoutkeep.ui.glossary_dialog import GlossaryDialog

    dialog = GlossaryDialog(line.window())
    dialog.set_document(document_path or None)
    if dialog.exec():
        configured = str(tunables.get("translation.glossary_path") or "").strip()
        if configured:
            line.setText(configured)


def _pick_file(line: QLineEdit) -> None:
    """Choose a glossary file; the filter matches what `Glossary.load` accepts."""
    chosen, _ = QFileDialog.getOpenFileName(
        line, UIStrings.TWEAKS_BROWSE, line.text().strip(), UIStrings.TWEAKS_GLOSSARY_FILTER
    )
    if chosen:
        line.setText(chosen)


class TweaksDialog(QDialog):
    #: "Show the welcome screen": it is dismissed for good on a first run.
    welcome_requested = Signal()
    """Edits tunables. `applied` fires whenever values change, so the app can refresh."""

    applied = Signal()

    def __init__(self, parent: QWidget | None = None, document_path: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.TWEAKS_TITLE)
        self.setMinimumWidth(620)
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

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self._footer)
        layout.addLayout(bottom)

    def _build_section(self, section: str) -> QWidget:
        page = QWidget()
        page.setObjectName("scrollPage")
        form = QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        if section == tunables.ADVANCED:
            banner = QLabel(UIStrings.TWEAKS_ADVANCED_BANNER)
            banner.setWordWrap(True)
            banner.setStyleSheet(
                f"color: {ThemeManager.current_palette().warning}; font-weight: 600;"
            )
            form.addRow(banner)

        current_group = ""
        for spec in tunables.definitions(section):
            if spec.group and spec.group != current_group:
                # Thirteen entries in one flat list read as a wall. The headings come from the
                # registry rather than being spelled out here, so a new tunable lands under the
                # right one by naming its key.
                current_group = spec.group
                heading = QLabel(spec.group)
                heading.setStyleSheet("font-weight: 700; margin-top: 10px;")
                form.addRow(heading)
            editor = _editor_for(spec)
            self._editors[spec.key] = editor
            field, _focus = _editor_holder(editor, spec, self._document_path)

            caption = QLabel(spec.help_text)
            caption.setProperty("class", "muted")
            caption.setWordWrap(True)

            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.setContentsMargins(0, 0, 0, 8)
            cell.addWidget(field)
            cell.addWidget(caption)
            if spec.warning:
                warn = QLabel(spec.warning)
                warn.setWordWrap(True)
                warn.setStyleSheet(f"color: {ThemeManager.current_palette().warning};")
                # The mark is drawn from the icon set rather than typed as a character: a font
                # glyph renders differently on every machine, and as an empty box where the
                # font has none.
                warn_icon = QLabel()
                warn_icon.setPixmap(
                    get_svg_icon(
                        "alert-triangle",
                        color=ThemeManager.current_palette().warning,
                        size=14,
                    ).pixmap(14, 14)
                )
                warn_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
                warn_row = QHBoxLayout()
                warn_row.setSpacing(6)
                warn_row.addWidget(warn_icon, 0, Qt.AlignmentFlag.AlignTop)
                warn_row.addWidget(warn, 1)
                cell.addLayout(warn_row)

            holder = QWidget()
            holder.setLayout(cell)
            # A word-wrapped QLabel reports its height for a given width, and a layout that
            # never fixes a width gets the wrong answer: the rows came out too short and the
            # warnings - the entire reason this tab is separated - were clipped and overlapped
            # the next row. Fixing the width lets heightForWidth resolve.
            holder.setMinimumWidth(_FIELD_WIDTH)
            holder.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
            )
            caption.setFixedWidth(_FIELD_WIDTH)
            caption.setMinimumHeight(caption.heightForWidth(_FIELD_WIDTH))
            if spec.warning:
                # The icon takes 14px plus the row spacing out of the field width.
                text_width = _FIELD_WIDTH - 20
                warn.setFixedWidth(text_width)
                warn.setMinimumHeight(warn.heightForWidth(text_width))

            row_label = QLabel(spec.label)
            row_label.setWordWrap(True)
            # Its own width, or the field column squeezes it until the wrapped lines of one
            # label run into the next one.
            row_label.setFixedWidth(_LABEL_WIDTH)
            row_label.setMinimumHeight(row_label.heightForWidth(_LABEL_WIDTH))
            row_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
            )
            form.addRow(row_label, holder)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    # -- actions -----------------------------------------------------------
    def apply_values(self) -> None:
        """Store every editor's value and persist. Out-of-range values are clamped."""
        for key, editor in self._editors.items():
            value = _editor_value(editor)
            if value is not None:
                tunables.set_value(key, value)
        tunables.save()
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
