"""Tests for UI multilingual support (i18n) and live language switching.

Arayüz çoklu dil desteği (Türkçe, İngilizce, Almanca) ve anlık dil değişimi testleri.
"""

from __future__ import annotations

from layoutkeep.ui.header import HeaderBar
from layoutkeep.ui.main_window import MainWindow
from layoutkeep.ui.settings import app_settings
from layoutkeep.ui.strings import UIStrings


def test_ui_strings_translations() -> None:
    # Farklı diller için UIStrings çevirilerini doğrular / Verifies UIStrings for different languages
    UIStrings.set_language("tr")
    assert UIStrings.APP_TITLE == "LayoutKeep"
    assert UIStrings.START_TRANSLATION_BTN == "Çeviriyi Başlat"
    assert UIStrings.LIGHT_MODE == "Açık Tema"

    UIStrings.set_language("en")
    assert UIStrings.APP_TITLE == "LayoutKeep"
    assert UIStrings.START_TRANSLATION_BTN == "Start Translation"
    assert UIStrings.LIGHT_MODE == "Light Mode"

    UIStrings.set_language("de")
    assert UIStrings.APP_TITLE == "LayoutKeep"
    assert UIStrings.START_TRANSLATION_BTN == "Übersetzung starten"
    assert UIStrings.LIGHT_MODE == "Heller Modus"

    # Reset to default
    UIStrings.set_language("tr")


def test_header_language_selector(qtbot) -> None:
    # Header üzerindeki dil seçici sinyalini ve arayüz güncellemesini test eder
    header = HeaderBar()
    qtbot.addWidget(header)

    emitted_langs: list[str] = []
    header.ui_language_changed.connect(emitted_langs.append)

    # Dil seçici İngilizce'ye getirildiğinde sinyal yayılmalı / Changing to English should emit signal
    header._ui_lang_combo.setCurrentIndex(1)  # 1: English
    assert "en" in emitted_langs

    # Almanca seçildiğinde / Changing to German
    header._ui_lang_combo.setCurrentIndex(2)  # 2: Deutsch
    assert "de" in emitted_langs


def test_main_window_live_language_switch(qtbot) -> None:
    # Ana pencerede dil değişiminin tüm alt bileşenleri anında güncellemesini test eder
    settings = app_settings()
    original_lang = settings.value("ui_language", "tr")

    try:
        window = MainWindow()
        qtbot.addWidget(window)

        # İngilizceye geçiş / Switch to English
        window._on_ui_language_changed("en")
        assert UIStrings.get_language() == "en"
        assert window._setup._start_btn.text() == "Start Translation"
        assert settings.value("ui_language") == "en"

        # Almancaya geçiş / Switch to German
        window._on_ui_language_changed("de")
        assert UIStrings.get_language() == "de"
        assert window._setup._start_btn.text() == "Übersetzung starten"
        assert settings.value("ui_language") == "de"

        # Türkçeye dönüş / Switch back to Turkish
        window._on_ui_language_changed("tr")
        assert UIStrings.get_language() == "tr"
        assert window._setup._start_btn.text() == "Çeviriyi Başlat"
        assert settings.value("ui_language") == "tr"

    finally:
        settings.setValue("ui_language", original_lang)
        UIStrings.set_language("tr")
