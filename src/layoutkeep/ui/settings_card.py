"""Kurulum ekranının ayarlar kartı / The setup screen's settings card.

Split out of `job_setup.py` (D-017: a class body over ~220 lines gets split). The card is one
visual unit - the icon-titled frame, the labelled rows in a grid whose label column cannot grow -
so the frame and the builder that fills it live together here.

The builder writes the widget references onto the setup screen by name, because the language
change and the theme refresh read them (`retranslate_ui`, `apply_theme`); `ProgressControlsBuilder`
does the same for the progress card. This module does not import job_setup at runtime - only for
the annotation - so there is no cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

if TYPE_CHECKING:  # yalnız tip için / annotation only: job_setup imports this module
    from layoutkeep.ui.job_setup import _JobSetupUiBuilder

#: The format box holds a short phrase; the path box holds a path but not an essay.
_FORMAT_BOX_WIDTH = 260

#: Enough for the longest field label, and no more.
_LABEL_COLUMN_WIDTH = 26


class SetupCard(QFrame):
    """Mockup-03 style card: accent-colored icon + bold title header, body below.

    İkonlu başlıklı kart. Tek sorumluluğu kart başlığını ve gövdesini sunmaktır.
    """

    def __init__(self, icon_name: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._icon_name = icon_name
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 18)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-size: 13px; font-weight: 700;")

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self._icon_label)
        title_row.addWidget(self._title_label)
        title_row.addStretch()

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(14, 12, 14, 14)
        self._outer.setSpacing(10)
        self._outer.addLayout(title_row)
        self.apply_theme()

    def add_body(self, layout) -> None:
        # Kart gövdesine düzen ekler / Adds a body layout into the card
        self._outer.addLayout(layout)

    def add_body_widget(self, w: QWidget) -> None:
        # Kart gövdesine widget ekler / Adds a body widget into the card
        self._outer.addWidget(w)

    def retitle(self, title: str) -> None:
        # Dil değişiminde başlığı tazeler / Refreshes the title on language change
        self._title_label.setText(title)

    def apply_theme(self) -> None:
        # İkonu aktif aksan rengiyle bozar / Paints the header icon with the active accent
        pal = ThemeManager.current_palette()
        self._icon_label.setPixmap(get_svg_icon(self._icon_name, color=pal.accent, size=18).pixmap(18, 18))


def _icon_label(icon_name: str, tooltip: str) -> QLabel:
    """A row marker: the icon says which row this is, the tooltip says it in words."""
    label = QLabel()
    label.setPixmap(
        get_svg_icon(icon_name, color=ThemeManager.current_palette().text_muted, size=18).pixmap(
            18, 18
        )
    )
    label.setToolTip(tooltip)
    label.setFixedWidth(20)
    return label


class SettingsCardBuilder:
    """Ayarlar kartını satırlarıyla kurar / Builds the settings card and its labelled rows."""

    def __init__(self, screen: _JobSetupUiBuilder) -> None:
        self._screen = screen

    def build(self) -> SetupCard:
        # Ayarlar kartını ikonlu başlıkla kurar / Builds the icon-titled settings card
        # "Kaynak Dil:" and "Hedef Dil:" between two language boxes said what the arrow says.
        screen = self._screen
        screen._src_label = _icon_label("globe", UIStrings.SOURCE_LANG_LABEL)
        screen._src_label.hide()
        screen._tgt_label = _icon_label("arrow-right", UIStrings.TARGET_LANG_LABEL)
        langs_row = QHBoxLayout()
        langs_row.setSpacing(8)
        langs_row.addWidget(screen._source_lang, 1)
        langs_row.addWidget(screen._tgt_label)
        langs_row.addWidget(screen._target_lang, 1)

        range_row = QHBoxLayout()
        range_row.addWidget(screen._range_mode)
        range_row.addWidget(screen._range_input)

        screen._out_fmt_label = _icon_label("file-type", UIStrings.OUTPUT_FORMAT_LABEL)
        screen._out_file_label = _icon_label("file-output", UIStrings.OUTPUT_FILE_LABEL)
        screen._langs_label = _icon_label("globe", UIStrings.LANGS_LABEL)
        screen._range_label = _icon_label("range", UIStrings.RANGE_LABEL)
        screen._provider_label = _icon_label("server", UIStrings.PROVIDER_LABEL)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        # Spare width belongs to the fields. Without this the grid shares it out evenly and
        # the label column grew to a third of the card, holding two words.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnMinimumWidth(0, _LABEL_COLUMN_WIDTH)
        grid.addWidget(screen._out_fmt_label, 0, 0)
        # No stretch and no second column: the longest entry here is a short phrase, and a
        # box the width of the card for it left the path below looking cramped by comparison.
        screen._output_format.setMaximumWidth(_FORMAT_BOX_WIDTH)
        grid.addWidget(screen._output_format, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(screen._output_path)
        out_row.addWidget(screen._browse_out_btn)
        out_row.addStretch()
        grid.addWidget(screen._out_file_label, 1, 0)
        grid.addLayout(out_row, 1, 1, 1, 2)
        grid.addWidget(screen._langs_label, 2, 0)
        grid.addLayout(langs_row, 2, 1, 1, 2)
        grid.addWidget(screen._range_label, 3, 0)
        grid.addLayout(range_row, 3, 1, 1, 2)
        grid.addWidget(screen._range_hint, 5, 1, 1, 2)
        grid.addWidget(screen._provider_label, 4, 0)
        grid.addWidget(screen._provider_profile_combo, 4, 1)
        grid.addWidget(screen._provider_btn, 4, 2)

        card = SetupCard("settings", UIStrings.SETTINGS_CARD_TITLE)
        card.add_body(grid)
        return card
