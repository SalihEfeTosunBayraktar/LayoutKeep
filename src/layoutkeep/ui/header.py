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
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.branding import LOGO_SIZE, logo_pixmap
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
    theme_toggled = Signal(bool)
    ui_language_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBar")
        self._init_ui()

    def _init_ui(self) -> None:
        # Başlık ve kontrolleri yerleştirir / Lays out title and controls
        self._logo_label = QLabel()
        self._logo_label.setObjectName("logoLabel")
        self._logo_label.setFixedSize(LOGO_SIZE + 4, LOGO_SIZE + 4)
        self._set_logo_pixmap()

        self._title_label = QLabel(UIStrings.APP_TITLE)
        self._title_label.setStyleSheet("font-size: 18px; font-weight: 800; letter-spacing: 0.5px;")

        self._subtitle_label = QLabel(UIStrings.APP_SUBTITLE)
        self._subtitle_label.setProperty("class", "muted")

        brand_layout = QVBoxLayout()
        brand_layout.addWidget(self._title_label)
        brand_layout.addWidget(self._subtitle_label)
        # Give way before the stepper does when the window is narrow, but only then:
        # QSizePolicy.Ignored discards the size hint outright and clipped the subtitle even
        # with room to spare. Minimum keeps the natural width until space actually runs out.
        self._subtitle_label.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred
        )

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
        main_layout.addWidget(self._logo_label)
        main_layout.addSpacing(8)
        main_layout.addLayout(brand_layout)
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
        main_layout.addWidget(self._tweaks_btn)
        main_layout.addWidget(self._theme_btn)

        self._apply_width_rules(self.width())
        self.set_active_step(1)

    #: Below this the subtitle goes; below the second the step labels shorten. The header is
    #: the widest thing in the window, so what it insists on is the window's minimum width.
    _SUBTITLE_MIN_WIDTH = 1000
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

        The stepper cannot be clipped - it is how the user knows where they are - and the
        brand subtitle carries no information the title does not. So the subtitle goes first
        and the step labels shorten second; both come back when the window is widened again.
        """
        self._subtitle_label.setVisible(width >= self._SUBTITLE_MIN_WIDTH)
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

    def _set_logo_pixmap(self) -> None:
        # Logo SVG'yi etikete render eder / Renders the logo SVG into the header label
        self._logo_label.setPixmap(logo_pixmap(LOGO_SIZE))

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

        self._tweaks_btn = QPushButton()
        self._tweaks_btn.setToolTip(UIStrings.TWEAKS_MENU)
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
        self._title_label.setText(UIStrings.APP_TITLE)
        self._subtitle_label.setText(UIStrings.APP_SUBTITLE)
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
