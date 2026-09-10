"""Language definitions and specialized combobox selector for LayoutKeep.

Yaygın dillerin tanımları ve çift dilli/kod uyumlu açılır dil kutusu bileşeni.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox

# Dünyada en yaygın kullanılan diller ve Türkçe adları / Widely used languages & Turkish names
LANG_DEFINITIONS: list[tuple[str, str]] = [
    ("tr", "Türkçe"),
    ("en", "İngilizce"),
    ("de", "Almanca"),
    ("fr", "Fransızca"),
    ("es", "İspanyolca"),
    ("it", "İtalyanca"),
    ("pt", "Portekizce"),
    ("ru", "Rusça"),
    ("zh", "Çince"),
    ("ja", "Japonca"),
    ("ko", "Korece"),
    ("ar", "Arapça"),
    ("az", "Azerbaycan Türkçesi"),
    ("nl", "Felemenkçe"),
    ("pl", "Lehçe"),
    ("uk", "Ukraynaca"),
    ("hi", "Hintçe"),
    ("fa", "Farsça"),
    ("el", "Yunanca"),
    ("cs", "Çekçe"),
    ("ro", "Rumence"),
    ("hu", "Macarca"),
    ("sv", "İsveççe"),
    ("no", "Norveççe"),
    ("da", "Danca"),
    ("fi", "Fince"),
    ("id", "Endonezce"),
    ("vi", "Vietnamca"),
    ("he", "İbranice"),
]

#: The same codes, named in each interface language. "tr (Türkçe)" in an English window is
#: not a translation gap, it is a language nobody asked to read.
_NAMES: dict[str, dict[str, str]] = {
    "tr": dict(LANG_DEFINITIONS),
    "en": {'tr': 'Turkish', 'en': 'English', 'de': 'German', 'fr': 'French', 'es': 'Spanish', 'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'az': 'Azerbaijani', 'nl': 'Dutch', 'pl': 'Polish', 'uk': 'Ukrainian', 'hi': 'Hindi', 'fa': 'Persian', 'el': 'Greek', 'cs': 'Czech', 'ro': 'Romanian', 'hu': 'Hungarian', 'sv': 'Swedish', 'no': 'Norwegian', 'da': 'Danish', 'fi': 'Finnish', 'id': 'Indonesian', 'vi': 'Vietnamese', 'he': 'Hebrew'},
    "de": {'tr': 'Türkisch', 'en': 'Englisch', 'de': 'Deutsch', 'fr': 'Französisch', 'es': 'Spanisch', 'it': 'Italienisch', 'pt': 'Portugiesisch', 'ru': 'Russisch', 'zh': 'Chinesisch', 'ja': 'Japanisch', 'ko': 'Koreanisch', 'ar': 'Arabisch', 'az': 'Aserbaidschanisch', 'nl': 'Niederländisch', 'pl': 'Polnisch', 'uk': 'Ukrainisch', 'hi': 'Hindi', 'fa': 'Persisch', 'el': 'Griechisch', 'cs': 'Tschechisch', 'ro': 'Rumänisch', 'hu': 'Ungarisch', 'sv': 'Schwedisch', 'no': 'Norwegisch', 'da': 'Dänisch', 'fi': 'Finnisch', 'id': 'Indonesisch', 'vi': 'Vietnamesisch', 'he': 'Hebräisch'},
}

#: Shown for the auto-detect entry, per interface language.
_AUTO_NAMES = {"tr": "Otomatik", "en": "Auto-detect", "de": "Automatisch"}


def definitions(ui_language: str) -> list[tuple[str, str]]:
    """The language list, named in `ui_language` (English when it has no names)."""
    names = _NAMES.get(ui_language) or _NAMES["en"]
    return [(code, names.get(code, fallback)) for code, fallback in LANG_DEFINITIONS]


def auto_name(ui_language: str) -> str:
    return _AUTO_NAMES.get(ui_language) or _AUTO_NAMES["en"]


# ISO dil kodları listesi / List of ISO language codes
LANGS: list[str] = [code for code, _ in LANG_DEFINITIONS]


class LanguageComboBox(QComboBox):
    # Çift dilli ve kod uyumlu açılır dil kutusu / Language combo supporting display and ISO codes

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def populate(self, langs: list[tuple[str, str]], include_auto: bool = False) -> None:
        # Dil listesini doldurur / Populates language list
        self.blockSignals(True)
        self.clear()
        if include_auto:
            from layoutkeep.ui.strings import UIStrings

            self.addItem(f"auto ({auto_name(UIStrings.get_language())})", "auto")
        for code, name in langs:
            self.addItem(f"{code} ({name})", code)
        self.blockSignals(False)

    def findText(self, text: str, flags: Qt.MatchFlag = Qt.MatchFlag.MatchExactly) -> int:
        # Metne veya ISO koduna göre öğe indeksini bulur / Finds item index by text or ISO code
        idx = super().findText(text, flags)
        if idx >= 0:
            return idx
        return self.findData(text)

    def setCurrentText(self, text: str) -> None:
        # Kod veya metin eşleşmesiyle seçimi günceller / Sets current selection by code or text
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
            return
        super().setCurrentText(text)

    def currentText(self) -> str:
        # Aktif dil kodunu döndürür / Returns active language code
        data = self.currentData()
        return str(data) if data is not None else super().currentText()
