"""Header bar widget for LayoutKeep: application branding, step indicator, and theme switcher.

Uygulama logosu, başlık, aktif adım göstergesi, arayüz dil seçici ve tema değiştiriciyi içeren üst çubuk.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager


def _short_step(label: str) -> str:
    """"1. Belge & Format" -> "Belge".

    The number is already in the circle beside the label, so dropping it costs nothing; what
    has to survive is the word that says which step this is.
    """
    without_number = label.split(". ", 1)[-1]
    return without_number.split(" &", 1)[0].split(" ", 1)[0].strip()


class HeaderBar(QFrame):
    # Üst gezinti ve durum çubuğu / Top navigation and status bar
    #: The settings button next to the theme toggle was clicked.
    tweaks_requested = Signal()
    help_requested = Signal()
    bar_requested = Signal()  # hand the run over to the floating bar
    # NOTE: kept for the window's own use; the header button was removed on request because it sat
    # in the header unable to act until a run started.
    theme_toggled = Signal(bool)
    ui_language_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBar")
        self._init_ui()

    def _init_ui(self) -> None:
        # Başlık ve kontrolleri yerleştirir / Lays out title and controls
        # No logo and no wordmark on this bar: the reader asked for a clean strip that carries the
        # step indicator and the controls, tinted a step apart from the page behind it.
        self._step_setup = QLabel(UIStrings.STEP_SETUP)
        self._step_progress = QLabel(UIStrings.STEP_PROGRESS)
        self._step_review = QLabel(UIStrings.STEP_REVIEW)

        # Mockup tarzı daire-numara adım göstergesi / Mockup-style numbered circle steps
        self._step_circles = []
        self._step_connectors: list[QLabel] = []
        for num, _text_label in ((1, self._step_setup), (2, self._step_progress), (3, self._step_review)):
            circle = QLabel(str(num))
            circle.setFixedSize(22, 22)
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_circles.append(circle)

        steps_layout = QHBoxLayout()
        steps_layout.setSpacing(8)
        for i, (circle, label) in enumerate(zip(self._step_circles, (self._step_setup, self._step_progress, self._step_review), strict=False)):
            steps_layout.addWidget(circle)
            steps_layout.addWidget(label)
            if i < 2:
                connector = QLabel("—")
                connector.setProperty("class", "muted")
                steps_layout.addWidget(connector)
                self._step_connectors.append(connector)

        self._init_controls()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 10)
        main_layout.addStretch(1)
        # The stepper is the one part that must never be cut: two stretches of equal weight
        # squeezed it between the brand and the controls, and at the window's real width the
        # labels came out as "1. Belge & For" and "3. Tamamland". It keeps its natural width
        # now and the empty space either side gives way instead.
        steps_holder = QWidget()
        steps_holder.setLayout(steps_layout)
        steps_holder.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        main_layout.addWidget(steps_holder)
        main_layout.addStretch(1)
        main_layout.addWidget(self._ui_lang_combo)
        main_layout.addWidget(self._help_btn)
        main_layout.addWidget(self._tweaks_btn)
        main_layout.addWidget(self._theme_btn)

        self._apply_width_rules(self.width())
        self.set_active_step(1)

    #: Below this the step labels shorten. The header is the widest thing in the window, so what
    #: it insists on is the window's minimum width.
    _SHORT_STEPS_MIN_WIDTH = 900
    #: Under this the labels go entirely. The numbered circles stay, and they are what marks
    #: the step you are on; a half-word ("Tamamlan") tells the user less than a number does.
    _STEP_LABELS_MIN_WIDTH = 800

    #: What the header can be squeezed to once the subtitle is hidden and the step labels are
    #: short. Qt would otherwise take the widest arrangement - everything present at once - as
    #: the minimum, and that became the whole window's minimum width.
    _NARROWEST = 660

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._NARROWEST), hint.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_width_rules(self.width())

    def _apply_width_rules(self, width: int) -> None:
        """Drop the least important text first, so nothing is ever cut mid-word.

        The stepper cannot be clipped - it is how the user knows where they are - so when the
        bar runs out of room the step labels shorten, and come back when it is widened again.
        """
        short = width < self._SHORT_STEPS_MIN_WIDTH
        labelled = width >= self._STEP_LABELS_MIN_WIDTH
        for label, full in (
            (self._step_setup, UIStrings.STEP_SETUP),
            (self._step_progress, UIStrings.STEP_PROGRESS),
            (self._step_review, UIStrings.STEP_REVIEW),
        ):
            label.setVisible(labelled)
            label.setText(_short_step(full) if short else full)
            label.setToolTip(full)
        for connector in self._step_connectors:
            connector.setVisible(labelled)
        for circle, full in zip(
            self._step_circles,
            (UIStrings.STEP_SETUP, UIStrings.STEP_PROGRESS, UIStrings.STEP_REVIEW), strict=False,
        ):
            circle.setToolTip(full)

    def _init_controls(self) -> None:
        # Dil ve tema denetimlerini kurar / Sets up language and theme controls
        self._ui_lang_combo = QComboBox()
        self._ui_lang_combo.setToolTip(UIStrings.UI_LANG_LABEL)
        for code, name in UIStrings.SUPPORTED_LANGUAGES:
            self._ui_lang_combo.addItem(name, code)
        cur_lang = UIStrings.get_language()
        idx_lang = self._ui_lang_combo.findData(cur_lang)
        if idx_lang >= 0:
            self._ui_lang_combo.setCurrentIndex(idx_lang)
        self._ui_lang_combo.currentIndexChanged.connect(self._on_lang_combo_changed)

        self._help_btn = QPushButton("?")
        self._help_btn.setToolTip(UIStrings.HELP_TITLE)
        self._help_btn.clicked.connect(self.help_requested.emit)

        self._tweaks_btn = QPushButton()
        self._tweaks_btn.setToolTip(UIStrings.TWEAKS_MENU)
        self._help_btn.setToolTip(UIStrings.HELP_TITLE)
        self._tweaks_btn.clicked.connect(self.tweaks_requested.emit)

        self._theme_btn = QPushButton()
        self._theme_btn.setToolTip(UIStrings.THEME_TOGGLE)
        self._theme_btn.clicked.connect(self._toggle_theme)
        self._update_theme_icon()

    def _on_lang_combo_changed(self) -> None:
        # Dil seçimi değiştiğinde sinyal yayar / Emits signal when UI language changes
        code = str(self._ui_lang_combo.currentData() or "tr")
        self.ui_language_changed.emit(code)

    def set_active_language(self, lang: str) -> None:
        # Seçili arayüz dilini günceller / Updates selected UI language in combobox
        idx = self._ui_lang_combo.findData(lang)
        if idx >= 0:
            self._ui_lang_combo.blockSignals(True)
            self._ui_lang_combo.setCurrentIndex(idx)
            self._ui_lang_combo.blockSignals(False)

    def retranslate_ui(self) -> None:
        # Başlık ve etiketleri güncel dilde yeniler / Retranslates header texts in active language
        self._step_setup.setText(UIStrings.STEP_SETUP)
        self._step_progress.setText(UIStrings.STEP_PROGRESS)
        self._step_review.setText(UIStrings.STEP_REVIEW)
        self._theme_btn.setToolTip(UIStrings.THEME_TOGGLE)
        self._tweaks_btn.setToolTip(UIStrings.TWEAKS_MENU)
        self._ui_lang_combo.setToolTip(UIStrings.UI_LANG_LABEL)

    def _toggle_theme(self) -> None:
        # Temayı açık/koyu arasında değiştirir / Toggles between light and dark theme
        new_state = not ThemeManager.is_dark()
        ThemeManager.set_dark(new_state)
        self._update_theme_icon()
        self.theme_toggled.emit(new_state)

    def _update_theme_icon(self) -> None:
        # Tema butonunun ikonunu günceller / Updates icon on theme button
        palette = ThemeManager.current_palette()
        icon_name = "theme_sun" if ThemeManager.is_dark() else "theme_moon"
        self._theme_btn.setIcon(get_svg_icon(icon_name, color=palette.accent))
        self._tweaks_btn.setIcon(get_svg_icon("sliders", color=palette.accent))

    def set_active_step(self, step_idx: int) -> None:
        # Aktif olan adımı görsel olarak vurgular / Highlights active workflow step
        labels = [self._step_setup, self._step_progress, self._step_review]
        palette = ThemeManager.current_palette()
        for idx, lbl in enumerate(labels, 1):
            circle = self._step_circles[idx - 1] if hasattr(self, "_step_circles") else None
            if idx == step_idx:
                lbl.setStyleSheet(f"font-weight: 700; color: {palette.accent};")
                if circle is not None:
                    circle.setStyleSheet(
                        f"background-color: {palette.accent}; color: {palette.accent_text};"
                        " border-radius: 11px; font-weight: 700; font-size: 11px;"
                    )
            elif idx < step_idx:
                lbl.setStyleSheet(f"color: {palette.text_muted}; font-weight: normal;")
                if circle is not None:
                    circle.setStyleSheet(
                        f"background-color: {palette.success}; color: {palette.accent_text};"
                        " border-radius: 11px; font-weight: 700; font-size: 11px;"
                    )
            else:
                lbl.setStyleSheet(f"color: {palette.text_muted}; font-weight: normal;")
                if circle is not None:
                    circle.setStyleSheet(
                        f"color: {palette.text_muted}; border: 1px solid {palette.border};"
                        " border-radius: 11px; font-size: 11px;"
                    )
