"""Tests for language definitions and LanguageComboBox.

Dil tanımları ve çift dilli açılır kutu bileşeni testleri.
"""

from __future__ import annotations

from layoutkeep.ui.languages import LANG_DEFINITIONS, LANGS, LanguageComboBox


def test_lang_definitions():
    # Temel dillerin listede olduğu doğrulanır / Verifies major languages are defined
    assert "tr" in LANGS
    assert "en" in LANGS
    assert "ru" in LANGS
    assert "zh" in LANGS
    assert "ja" in LANGS
    assert "ko" in LANGS
    assert "ar" in LANGS
    assert "az" in LANGS
    assert len(LANGS) >= 25


def test_language_combobox(qtbot):
    # LanguageComboBox bileşeninin seçim ve kod döndürme yetenekleri test edilir
    box = LanguageComboBox()
    qtbot.addWidget(box)

    box.populate(LANG_DEFINITIONS, include_auto=True)
    assert box.count() == len(LANG_DEFINITIONS) + 1

    # auto seçimi
    box.setCurrentText("auto")
    assert box.currentText() == "auto"

    # Kod ile seçim yapma
    box.setCurrentText("ru")
    assert box.currentText() == "ru"
    assert "Rusça" in box.itemText(box.currentIndex())

    box.setCurrentText("zh")
    assert box.currentText() == "zh"
    assert "Çince" in box.itemText(box.currentIndex())

    box.setCurrentText("ar")
    assert box.currentText() == "ar"
    assert "Arapça" in box.itemText(box.currentIndex())

    # findText hem kod hem görünen metin ile bulabilmeli
    idx_ru = box.findText("ru")
    assert idx_ru >= 0
    idx_ru_full = box.findText("ru (Rusça)")
    assert idx_ru_full == idx_ru
