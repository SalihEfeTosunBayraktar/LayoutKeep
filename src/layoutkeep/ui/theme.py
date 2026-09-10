"""Theme manager for LayoutKeep: compiles QSS from design tokens for Light and Dark themes.

Açık ve koyu temalar için tasarım token'larından modern Qt Style Sheet (QSS) derleyen tema modülü.
"""

from __future__ import annotations

from layoutkeep.ui.tokens import (
    DARK_PALETTE,
    FONT_FAMILY,
    FONT_FAMILY_MONO,
    LIGHT_PALETTE,
    RADIUS_MD,
    RADIUS_SM,
    ColorPalette,
)


def _build_qss(palette: ColorPalette) -> str:
    # Belirli bir palet için QSS stil metnini derler / Compiles QSS style string for a given palette
    return f"""
    QMainWindow, QStackedWidget, QWidget#rootWindow {{
        background-color: {palette.background};
        color: {palette.text_primary};
        font-family: {FONT_FAMILY};
        font-size: 13px;
    }}
    QFrame#headerBar, QFrame#headerBar QLabel, QFrame#headerBar QComboBox {{
        background: transparent;
        color: {palette.text_primary};
    }}
    QGroupBox, QFrame.card {{
        background-color: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_MD};
        margin-top: 8px;
        padding: 14px;
    }}
    QDialog, QMessageBox {{
        background-color: {palette.background};
        color: {palette.text_primary};
    }}
    /* Nothing here styled a message box, so Windows painted its background with the desktop's
       dark mode while the QLabel rule below coloured the text for our light palette: dark text
       on a dark ground, and an error nobody could read. */
    QMessageBox QLabel {{
        color: {palette.text_primary};
    }}
    /* A list left unstyled is painted by the desktop, which in light mode meant a dark panel
       inside a white dialog - the same mismatch that made an error message unreadable. */
    /* Same rule as the list, for the same reason: an unstyled view is painted by the desktop,
       so a light dialog came with a dark panel inside it. */
    /* The right-click menu on the endpoint list. Found by the coverage test rather than by
       looking: unstyled, it is drawn by the desktop, so a light theme got a dark menu. */
    QMenu {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 18px 6px 12px;
        border-radius: {RADIUS_SM};
    }}
    QMenu::item:selected {{
        background-color: {palette.accent};
        color: {palette.accent_text};
    }}
    QMenu::separator {{
        height: 1px;
        background: {palette.border};
        margin: 4px 6px;
    }}
    QTabWidget::pane {{
        background-color: {palette.background};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {palette.surface};
        color: {palette.text_secondary};
        border: 1px solid {palette.border};
        border-bottom: none;
        border-top-left-radius: {RADIUS_SM};
        border-top-right-radius: {RADIUS_SM};
        padding: 6px 14px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {palette.background};
        color: {palette.text_primary};
        font-weight: 600;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    /* Only the page a scroll area carries, named for the purpose. A wildcard here reaches
       the spin boxes and text fields inside it too, and they came out with no background at
       all - a value box drawn as a bare line. */
    QWidget#scrollPage {{
        background: transparent;
    }}
    QTreeView {{
        /* No dotted focus rectangle drawn on top of the selected row. */
        outline: 0;
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 4px;
    }}
    QTreeView::item {{
        /* A row needs a stated height here: with padding alone the selected row came out
           shorter than its own text and clipped it. */
        min-height: 24px;
        padding: 2px 4px;
        border-radius: {RADIUS_SM};
    }}
    QTreeView::item:selected {{
        background-color: {palette.accent};
        color: {palette.accent_text};
    }}
    QListWidget {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 6px 8px;
        border-radius: {RADIUS_SM};
    }}
    QListWidget::item:selected {{
        background-color: {palette.accent};
        color: {palette.accent_text};
    }}
    QListWidget::item:disabled {{
        color: {palette.text_muted};
        font-size: 11px;
        font-weight: 600;
    }}
    QGroupBox {{
        color: {palette.text_primary};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 6px;
        color: {palette.text_secondary};
    }}
    QLabel {{
        color: {palette.text_primary};
        background: transparent;
    }}
    QLabel.secondary {{
        color: {palette.text_secondary};
    }}
    QLabel.muted {{
        color: {palette.text_muted};
        font-size: 11px;
    }}
    #dropZone {{
        background-color: {palette.dropzone_bg};
        border: 2px dashed {palette.dropzone_border};
        border-radius: {RADIUS_MD};
        padding: 16px;
    }}
    #dropZone[dragHover="true"] {{
        background-color: {palette.surface_hover};
        border: 2px dashed {palette.border_focus};
    }}
    /* The settings dialog is built out of these and nothing styled them, so their value was
       drawn by the desktop and vanished against the panel: a number box with no number. */
    QSpinBox, QDoubleSpinBox {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 6px 8px;
        min-height: 20px;
        selection-background-color: {palette.accent};
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {palette.border_focus};
    }}
    QLineEdit {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 7px 10px;
        selection-background-color: {palette.accent};
    }}
    QLineEdit:focus {{
        border: 2px solid {palette.border_focus};
    }}
    QComboBox {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 7px 12px;
        min-height: 20px;
    }}
    QComboBox:focus {{
        border: 2px solid {palette.border_focus};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        selection-background-color: {palette.accent};
        selection-color: {palette.accent_text};
        padding: 4px;
    }}
    QPushButton {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        padding: 8px 16px;
        font-weight: 500;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {palette.surface_hover};
        border-color: {palette.border_focus};
    }}
    QPushButton:pressed {{
        background-color: {palette.surface_active};
    }}
    QPushButton.primary {{
        background-color: {palette.accent};
        color: {palette.accent_text};
        border: none;
        font-weight: 600;
        padding: 10px 20px;
        border-radius: {RADIUS_MD};
        font-size: 14px;
    }}
    QPushButton.primary:hover {{
        background-color: {palette.accent_hover};
    }}
    QProgressBar {{
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        background-color: {palette.surface_active};
        text-align: center;
        color: #ffffff;
        font-weight: bold;
        font-size: 12px;
        height: 24px;
    }}
    QProgressBar::chunk {{
        background-color: {palette.accent};
        border-radius: {RADIUS_SM};
    }}
    QTextEdit, QPlainTextEdit {{
        background-color: {palette.surface};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SM};
        font-family: {FONT_FAMILY_MONO};
    }}
    """


class ThemeManager:
    # Uygulama genelinde tema yönetimini sağlar / Manages themes across the application
    _is_dark: bool = False

    @classmethod
    def is_dark(cls) -> bool:
        return cls._is_dark

    @classmethod
    def set_dark(cls, dark: bool) -> None:
        cls._is_dark = dark

    @classmethod
    def current_palette(cls) -> ColorPalette:
        return DARK_PALETTE if cls._is_dark else LIGHT_PALETTE

    @classmethod
    def get_stylesheet(cls) -> str:
        return _build_qss(cls.current_palette())
