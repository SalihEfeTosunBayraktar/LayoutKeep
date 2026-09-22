"""Pencerenin görünümü: tema ve arayüz dili / The window's appearance: theme and interface language.

Tema tercihi ve arayüz dili kaydedilir ve bütün ekranlara uygulanır. Bu iki tercih pencere
tarafından üç yerden değiştirilir (kayıtlı değeri geri yükleme, başlık çubuğundaki düğme,
karşılama ekranı) ve üçü de aynı yoldan geçer, yoksa biri ötekini ezer.

Kendi Qt durumunu tutmaz: pencere ayarları, başlık çubuğunu ve tazelenecek ekranları verir.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QWidget

from layoutkeep.ui.header import HeaderBar
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager


class WindowAppearance:
    """Saves and applies the theme and the interface language for the whole window."""

    def __init__(
        self,
        settings,
        header: HeaderBar,
        screens: Callable[[], tuple[QWidget, ...]],
        step: Callable[[], int],
    ) -> None:
        self._settings = settings
        self._header = header
        self._screens = screens
        self._step = step

    # ------------------------------------------------------------------- tema
    def restore_theme(self) -> None:
        # Kayıtlı tema tercihini uygular / Applies saved theme preference
        is_dark = self._settings.value("dark_mode", False, type=bool)
        ThemeManager.set_dark(is_dark)
        self.apply_theme()

    def store_theme(self, is_dark: bool) -> None:
        # Tema değiştiğinde QSS'i yeniler ve kaydeder / Refreshes QSS and saves on theme change
        self._settings.setValue("dark_mode", is_dark)
        self.apply_theme()

    def apply_theme(self) -> None:
        # Güncel stil sayfasını tüm uygulamaya uygular / Applies current stylesheet to app
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(ThemeManager.get_stylesheet())
        for screen in self._screens():
            screen.apply_theme()
        self._header.set_active_step(self._step())

    # -------------------------------------------------------------------- dil
    def restore_language(self) -> None:
        # Kayıtlı arayüz dilini yükler ve uygular / Restores and applies saved UI language
        lang = str(self._settings.value("ui_language", "en"))
        UIStrings.set_language(lang)
        self._header.set_active_language(lang)
        self.retranslate()

    def store_language(self, lang: str) -> None:
        # Arayüz dili değiştiğinde ayarı kaydeder ve metinleri günceller / Handles UI language change
        self._settings.setValue("ui_language", lang)
        UIStrings.set_language(lang)
        self.retranslate()

    def retranslate(self) -> None:
        # Tüm alt bileşenlerin metinlerini güncel dilde yeniler / Retranslates all subwidgets
        self._header.retranslate_ui()
        for screen in self._screens():
            screen.retranslate_ui()
