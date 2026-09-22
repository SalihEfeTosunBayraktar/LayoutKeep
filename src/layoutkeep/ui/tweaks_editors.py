"""Gelişmiş ayarlar penceresinin düzenleyicileri, satırları ve sayfaları.

Bir ayar satırı şunlardan oluşur: türüne uygun düzenleyici (sayı, anahtar, dosya yolu, seçenek),
açıklaması, uyarısı ve varsa uyarının arkasındaki ölçüm. Genişlikler sabittir: satır kaydıran bir
QLabel yüksekliğini ancak bilinen bir genişlikte doğru bildirir - sabit olmadığında satırlar kısa
çıkıyor ve uyarılar kırpılıp alt satırın üstüne biniyordu.

Bu modül TweaksDialog'a bağlı değildir: satırları kurar, düzenleyicileri verilen sözlüğe yazar.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
)

from layoutkeep.core import tunables
from layoutkeep.ui.collapsible import CollapsibleSection
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

#: Width the label column is fixed to, for the same reason.
LABEL_WIDTH = 210

#: Width the value column is fixed to. Word-wrapped help and warning text needs a known
#: width before it can report the height it will occupy.
FIELD_WIDTH = 300
# Wrapped labels need a fixed width to resolve their height - and to stop the dialog stretching to
# the length of the longest sentence it shows.
TEXT_WIDTH = LABEL_WIDTH + FIELD_WIDTH + 40


def editor_for(spec: tunables.Tunable) -> QWidget:
    """Türüne uygun düzenleyici üretir / Builds the editor matching the tunable's type.

    Four kinds, not two: a switch (the translation memory) and a file path (the glossary) are
    settings the same way the numbers are, and they belong on the same page with the same help
    text - not in a second dialog the user has to find.
    """
    value = tunables.get(spec.key)
    if spec.choices:
        combo = QComboBox()
        for choice_value, choice_label in spec.choices:
            combo.addItem(choice_label, choice_value)
        index = combo.findData(str(value or ""))
        combo.setCurrentIndex(index if index >= 0 else 0)
        # A combo sizes itself to its longest entry, and one entry reading "yan yana (cift dilli PDF)"
        # dragged the dialog's sizeHint - and with it the dialog - out to 1322 px, while the window
        # already sat at 760. The widest field wins; every label stays readable in the tooltip.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(22)
        combo.setMaximumWidth(FIELD_WIDTH)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, combo.sizePolicy().verticalPolicy())
        combo.setToolTip(" · ".join(label for _value, label in spec.choices))
        return combo
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


def editor_holder(
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


def build_row(
    spec: tunables.Tunable, editor: QWidget, document_path: str = ""
) -> tuple[QLabel, QWidget]:
    """One settings row: its label on the left, and the field with its text on the right."""
    field, _focus = editor_holder(editor, spec, document_path)

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

    if spec.evidence:
        # The measurement behind the warning, kept apart from it: a row whose warning ran to
        # five hundred characters read as a wall of orange, and the numbers stopped being
        # read at all. Muted and a size down, so it is there when looked for.
        proof = QLabel("Ölçüm: " + spec.evidence)
        proof.setWordWrap(True)
        proof.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        proof_font = proof.font()
        proof_font.setPointSizeF(max(7.0, proof_font.pointSizeF() - 1.0))
        proof.setFont(proof_font)
        proof.setStyleSheet(f"color: {ThemeManager.current_palette().text_muted};")
        proof_row = QHBoxLayout()
        proof_row.setSpacing(6)
        spacer = QLabel()
        spacer.setFixedWidth(20)
        proof_row.addWidget(spacer, 0, Qt.AlignmentFlag.AlignTop)
        proof_row.addWidget(proof, 1)
        cell.addLayout(proof_row)

    holder = QWidget()
    holder.setLayout(cell)
    # A word-wrapped QLabel reports its height for a given width, and a layout that
    # never fixes a width gets the wrong answer: the rows came out too short and the
    # warnings - the entire reason this tab is separated - were clipped and overlapped
    # the next row. Fixing the width lets heightForWidth resolve.
    holder.setMinimumWidth(FIELD_WIDTH)
    holder.setSizePolicy(
        QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
    )
    caption.setFixedWidth(FIELD_WIDTH)
    caption.setMinimumHeight(caption.heightForWidth(FIELD_WIDTH))
    if spec.warning:
        # The icon takes 14px plus the row spacing out of the field width.
        text_width = FIELD_WIDTH - 20
        warn.setFixedWidth(text_width)
        warn.setMinimumHeight(warn.heightForWidth(text_width))

    row_label = QLabel(spec.label)
    row_label.setWordWrap(True)
    # Its own width, or the field column squeezes it until the wrapped lines of one
    # label run into the next one.
    row_label.setFixedWidth(LABEL_WIDTH)
    row_label.setMinimumHeight(row_label.heightForWidth(LABEL_WIDTH))
    row_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    return row_label, holder


def build_section_page(
    section: str, editors: dict[str, Any], document_path: str = ""
) -> QScrollArea:
    """One tab: its groups as folding blocks, every setting inside them as a row."""
    page = QWidget()
    page.setObjectName("scrollPage")
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(6)

    if section == tunables.ADVANCED:
        banner = QLabel(UIStrings.TWEAKS_ADVANCED_BANNER)
        banner.setWordWrap(True)
        banner.setFixedWidth(TEXT_WIDTH)
        banner.setMinimumHeight(banner.heightForWidth(TEXT_WIDTH))
        banner.setStyleSheet(
            f"color: {ThemeManager.current_palette().warning}; font-weight: 600;"
        )
        outer.addWidget(banner)

    # Entries are grouped by the registry's `group` field, and each group folds away. A flat list
    # of a hundred rows is a wall, and a folded group is also out of the layout's size hint,
    # which is what keeps the window from opening as wide as its longest warning text.
    sections: list[CollapsibleSection] = []
    body: QFormLayout | None = None
    current_group: str | None = None
    for spec in tunables.definitions(section):
        group = spec.group or "OTHER"
        # The registry stores a stable key, not a translated word: the headings were the one
        # part of this dialog that stayed Turkish inside an English window. Resolved here, so
        # the same key reads as "Çeviri", "Translation" or "Übersetzung" as the reader chose.
        group_label = UIStrings.get(f"TWEAKS_GROUP_{group}")
        if group != current_group:
            current_group = group
            section_widget = CollapsibleSection(group_label, expanded=not sections)
            body = QFormLayout()
            body.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            body.setContentsMargins(12, 0, 0, 0)
            body.setSpacing(6)
            section_widget.set_body_layout(body)
            outer.addWidget(section_widget)
            sections.append(section_widget)
        if body is None:  # cannot happen: the first entry always opens a section
            raise RuntimeError("tweaks section built without a group body")
        editor = editor_for(spec)
        editors[spec.key] = editor
        row_label, holder = build_row(spec, editor, document_path)
        body.addRow(row_label, holder)

    # The sections hug their headings instead of sharing out the empty height. Without this the
    # stretch goes to the sections themselves and the collapsed headings float apart - measured
    # at 108px between headings whose own height is 35px, which is what the reader saw as
    # "why is there so much space between them".
    outer.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll
