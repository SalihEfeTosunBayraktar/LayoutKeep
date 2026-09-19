"""The screen a first run starts on.

WHY THIS EXISTS: the application opens straight onto a form - document, languages, provider - and
assumes the reader already knows what a provider is, what "lossless" means here, or why a local
model needs a context setting. The user asked for a detailed welcome that answers those questions,
lets the language and the theme be chosen before anything else, and can be skipped without
punishment. Page copy lives in `welcome_text.py`; this is the behaviour around it.
"""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui import welcome_text
from layoutkeep.ui.settings import app_settings
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

#: Height of the body, so the dialog does not resize between pages (which reads as a glitch).
_BODY_HEIGHT = 340

#: Which extra block a page carries beyond title/lead/bullets.
_EXTRA = {"first": "float", "provider": "local_hint"}


def _label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class WelcomeDialog(QDialog):
    """Five pages: what this is, how to start, who translates, what decides quality, done."""

    language_changed = Signal(str)
    theme_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("welcomeDialog")
        self.setWindowTitle("LayoutKeep")
        self.setModal(True)
        self.setMinimumSize(700, 540)
        self._index = 0
        self._pages: list[QWidget] = []
        self._build()
        self.apply_theme()
        self.retranslate_ui()
        self._go(0)

    # ------------------------------------------------------------------ building

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        self._heading = QLabel()
        self._heading.setObjectName("welcomeHeading")
        self._dots = QLabel()
        self._dots.setObjectName("welcomeDots")
        header = QHBoxLayout()
        header.addWidget(self._heading, 1)
        header.addWidget(self._dots, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)

        self._stack = QStackedWidget()
        self._stack.setFixedHeight(_BODY_HEIGHT)
        for key in welcome_text.PAGES:
            page = self.build_page(key)
            self._pages.append(page)
            self._stack.addWidget(page)
        outer.addWidget(self._stack, 1)

        self._never = QCheckBox()
        self._never.setChecked(True)
        self._skip = QPushButton()
        self._skip.setObjectName("welcomeGhost")
        self._skip.clicked.connect(self._finish)
        self._back = QPushButton()
        self._back.setObjectName("welcomeGhost")
        self._back.clicked.connect(lambda: self._go(self._index - 1))
        self._next = QPushButton()
        self._next.setObjectName("welcomePrimary")
        self._next.clicked.connect(self._advance)
        footer = QHBoxLayout()
        footer.addWidget(self._never)
        footer.addStretch(1)
        footer.addWidget(self._skip)
        footer.addWidget(self._back)
        footer.addWidget(self._next)
        outer.addLayout(footer)

    def build_page(self, key: str) -> QWidget:
        """One page, in the language currently in force.

        Public because `retranslate_ui` rebuilds a page rather than walking its labels: the copy is
        data from `welcome_text`, so rebuilding is simpler than matching strings, and a page is
        cheap enough (five labels) that the difference does not show.
        """
        language = UIStrings.get_language()
        page = QWidget()
        page.setProperty("welcome_page", key)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_label(welcome_text.text(language, key, "title"), "welcomeTitle"))
        lead = welcome_text.text(language, key, "lead")
        if lead:
            layout.addWidget(_label(lead, "welcomeBody"))
        bullets = welcome_text.text(language, key, "bullets")
        if bullets:
            layout.addWidget(_label(bullets, "welcomeBullets"))
        extra = _EXTRA.get(key)
        if extra:
            layout.addWidget(_label(welcome_text.text(language, key, extra), "welcomeHint"))
        if key == "hello":
            layout.addWidget(self.build_choices())
        layout.addStretch(1)
        return page

    def build_choices(self) -> QFrame:
        """The one place a first run can set language and theme before anything else."""
        card = QFrame()
        card.setObjectName("welcomeCard")
        column = QVBoxLayout(card)
        self._setup_label = _label(welcome_text.text(UIStrings.get_language(), "hello", "setup"), "welcomeBody")
        column.addWidget(self._setup_label)
        self._language = QComboBox()
        for code, label in UIStrings.SUPPORTED_LANGUAGES:
            self._language.addItem(label, code)
        self._language.setCurrentIndex(
            max(0, [code for code, _ in UIStrings.SUPPORTED_LANGUAGES].index(UIStrings.get_language()))
        )
        self._language.currentIndexChanged.connect(self._on_language)
        self._theme = QPushButton()
        self._theme.clicked.connect(self._on_theme)
        picks = QHBoxLayout()
        picks.addWidget(self._language)
        picks.addWidget(self._theme)
        picks.addStretch(1)
        column.addLayout(picks)
        return card

    # -------------------------------------------------------------------- actions

    def _on_language(self) -> None:
        code = self._language.currentData()
        UIStrings.set_language(code)
        self.retranslate_ui()
        self.language_changed.emit(code)

    def _on_theme(self) -> None:
        ThemeManager.set_dark(not ThemeManager.is_dark())
        self.apply_theme()
        self._refresh_theme_button()
        self.theme_changed.emit(ThemeManager.is_dark())

    def _refresh_theme_button(self) -> None:
        # The button offers the theme you are not in, so its label follows the current one.
        self._theme.setText(
            UIStrings.get("DARK_MODE") if ThemeManager.is_dark() else UIStrings.get("LIGHT_MODE")
        )

    def _advance(self) -> None:
        if self._index >= len(self._pages) - 1:
            self._finish()
        else:
            self._go(self._index + 1)

    def _go(self, index: int) -> None:
        """Show a page, fading it in: the user asked for motion, and a hard cut reads as a repaint."""
        if not 0 <= index < len(self._pages):
            return
        self._index = index
        self._stack.setCurrentIndex(index)
        effect = QGraphicsOpacityEffect(self._stack.currentWidget())
        self._stack.currentWidget().setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(170)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._refresh_navigation()

    def _finish(self) -> None:
        app_settings().setValue("welcome_shown", True)
        self.accept()

    def _refresh_navigation(self) -> None:
        last = self._index == len(self._pages) - 1
        self._dots.setText(" ".join("●" if i <= self._index else "○" for i in range(len(self._pages))))
        self._next.setText(
            welcome_text.text(UIStrings.get_language(), "done", "start" if last else "next")
        )
        self._back.setText(welcome_text.text(UIStrings.get_language(), "done", "back"))
        self._back.setVisible(self._index > 0)
        self._skip.setVisible(not last)

    # --------------------------------------------------------------- presentation

    def retranslate_ui(self) -> None:
        language = UIStrings.get_language()
        self._heading.setText(welcome_text.text(language, "hello", "title"))
        self._never.setText(welcome_text.text(language, "done", "never"))
        self._skip.setText(welcome_text.text(language, "done", "skip"))
        for index, key in enumerate(welcome_text.PAGES):
            rebuilt = self.build_page(key)
            previous = self._pages[index]
            self._stack.insertWidget(index, rebuilt)
            self._stack.removeWidget(previous)
            previous.deleteLater()
            self._pages[index] = rebuilt
        # After the rebuild: `build_choices` makes a fresh theme button, and setting its label
        # before that would set it on the widget that has just been thrown away.
        self._refresh_theme_button()
        self._stack.setCurrentIndex(self._index)
        self._refresh_navigation()

    def apply_theme(self) -> None:
        palette = ThemeManager.current_palette()
        self.setStyleSheet(
            f"#welcomeDialog {{ background:{palette.background}; }}"
            f"#welcomeHeading {{ color:{palette.text_primary}; font-size:20px; font-weight:600; }}"
            f"#welcomeTitle {{ color:{palette.text_primary}; font-size:16px; font-weight:600; }}"
            f"#welcomeBody {{ color:{palette.text_secondary}; font-size:13px; }}"
            f"#welcomeBullets {{ color:{palette.text_primary}; font-size:13px; }}"
            f"#welcomeHint {{ color:{palette.text_muted}; font-size:12px; }}"
            f"#welcomeDots {{ color:{palette.accent}; font-size:12px; }}"
            f"#welcomeCard {{ background:{palette.surface}; border:1px solid {palette.border};"
            f" border-radius:10px; }}"
            f"QPushButton#welcomePrimary {{ background:{palette.accent}; color:{palette.accent_text};"
            f" border:none; border-radius:8px; padding:8px 18px; font-weight:600; }}"
            f"QPushButton#welcomeGhost {{ background:transparent; color:{palette.text_secondary};"
            f" border:1px solid {palette.border}; border-radius:8px; padding:8px 14px; }}"
            f"QCheckBox {{ color:{palette.text_muted}; }}"
        )
