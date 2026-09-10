"""Model catalog, classification and grouped selector widget for LayoutKeep.

Model listelerini üretici ve ailelerine göre sınıflandıran, anlık arama ve filtreleme sunan bileşen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.theme import ThemeManager

# Üretici / Model Ailesi Eşleşmeleri / Vendor and model family pattern mappings
VENDOR_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("DeepSeek", ("deepseek",)),
    ("Meta / Llama", ("llama", "meta-llama", "codellama", "alpaca", "vicuna")),
    ("Alibaba / Qwen", ("qwen", "qwq")),
    ("Mistral AI", ("mistral", "mixtral", "codestral", "ministral", "pixtral")),
    ("Google / Gemma", ("gemma", "gemini", "google/")),
    ("Microsoft / Phi", ("phi", "microsoft/")),
    ("OpenAI", ("gpt", "o1-", "o1", "o3-", "o3", "text-embedding", "dall-e")),
    ("Anthropic / Claude", ("claude", "anthropic/")),
    ("Cohere", ("command", "aya", "c4ai")),
]
OTHER_VENDOR = "Diğer Modeller"
ALL_VENDORS = "Tüm Üreticiler"


def classify_vendor(model_id: str) -> str:
    # Model adına veya yoluna göre üretici ailesini tespit eder / Classifies vendor family by model ID
    lower = model_id.lower()
    if "/" in lower:
        org = lower.split("/", 1)[0]
        for vendor_name, patterns in VENDOR_PATTERNS:
            if any(p in org for p in patterns):
                return vendor_name

    for vendor_name, patterns in VENDOR_PATTERNS:
        if any(p in lower for p in patterns):
            return vendor_name
    return OTHER_VENDOR


def group_and_filter_models(
    models: list[str],
    search: str = "",
    vendor: str = "",
) -> dict[str, list[str]]:
    # Modelleri arama ve üretici filtresine göre gruplar / Filters and groups models by search and vendor
    query = search.strip().lower()
    active_vendor = vendor.strip()

    grouped: dict[str, list[str]] = {}
    for name, _ in VENDOR_PATTERNS:
        grouped[name] = []
    grouped[OTHER_VENDOR] = []

    for m in models:
        if query and query not in m.lower():
            continue
        v = classify_vendor(m)
        if active_vendor and active_vendor != ALL_VENDORS and v != active_vendor:
            continue
        grouped[v].append(m)

    return {k: v for k, v in grouped.items() if v}


class ModelSelectorWidget(QWidget):
    # Arama, üretici filtreleme ve gruplu model seçim bileşeni / Searchable & grouped model selector
    model_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_models: list[str] = []
        self._item_model = QStandardItemModel(self)
        self._init_ui()

    def _init_ui(self) -> None:
        # Arayüz elemanlarını kurar / Initializes UI controls
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Model ara… (örn: llama, qwen, 7b)")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.addAction(get_svg_icon("search", size=14), QLineEdit.ActionPosition.LeadingPosition)

        self._vendor_combo = QComboBox()
        self._vendor_combo.addItem(ALL_VENDORS)
        for name, _ in VENDOR_PATTERNS:
            self._vendor_combo.addItem(name)
        self._vendor_combo.addItem(OTHER_VENDOR)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setModel(self._item_model)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(self._search_input, stretch=2)
        top_row.addWidget(self._vendor_combo, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(top_row)
        layout.addWidget(self._model_combo)

        self._search_input.textChanged.connect(self._on_filter_changed)
        self._vendor_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._model_combo.currentTextChanged.connect(self._on_combo_text_changed)

    def _on_filter_changed(self) -> None:
        # Filtre veya arama değiştiğinde listeyi günceller / Updates list when filter or search changes
        current = self.currentText()
        grouped = group_and_filter_models(
            self._all_models,
            search=self._search_input.text(),
            vendor=self._vendor_combo.currentText(),
        )
        self._populate_model_combo(grouped, preserve_text=current)

    def _populate_model_combo(self, grouped: dict[str, list[str]], preserve_text: str = "") -> None:
        # Gruplanmış modelleri combobox modeline aktarır / Populates grouped items into combobox model
        self._model_combo.blockSignals(True)
        self._item_model.clear()

        all_matching = [m for m_list in grouped.values() for m in m_list]
        has_multiple_groups = len(grouped) > 1

        for vendor, models in grouped.items():
            if has_multiple_groups:
                header = QStandardItem(f"── {vendor} ({len(models)}) ──")
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setForeground(QColor(ThemeManager.current_palette().text_muted))
                font = QFont()
                font.setBold(True)
                header.setFont(font)
                self._item_model.appendRow(header)

            for m in models:
                self._item_model.appendRow(QStandardItem(m))

        if preserve_text and preserve_text in all_matching:
            self._model_combo.setEditText(preserve_text)
            idx = self._model_combo.findText(preserve_text)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
        elif all_matching:
            first_idx = 1 if has_multiple_groups else 0
            self._model_combo.setCurrentIndex(first_idx)
            self._model_combo.setEditText(all_matching[0])
        elif preserve_text:
            self._model_combo.setEditText(preserve_text)

        self._model_combo.blockSignals(False)
        self._on_combo_text_changed(self.currentText())

    def _on_combo_text_changed(self, text: str) -> None:
        # Model metni değiştiğinde sinyal yayar / Emits signal when model text changes
        self.model_changed.emit(text.strip())

    def set_models(self, models: list[str]) -> None:
        # Model listesini yükler ve arayüzü günceller / Loads model list and updates UI
        self._all_models = list(models)
        self._on_filter_changed()

    def all_models(self) -> list[str]:
        # Tüm ham model listesini döndürür / Returns raw model list
        return list(self._all_models)

    def currentText(self) -> str:
        # Seçili veya girilmiş model metnini döndürür / Returns active model text
        return self._model_combo.currentText().strip()

    def setEditText(self, text: str) -> None:
        # Combobox düzenleme metnini ayarlar / Sets combobox edit text
        self._model_combo.setEditText(text)
        idx = self._model_combo.findText(text)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        self._on_combo_text_changed(text)

    def addItem(self, text: str) -> None:
        # Tek bir model ekler / Adds a single model
        if text and text not in self._all_models:
            self._all_models.append(text)
        self._on_filter_changed()
        self.setEditText(text)

    def addItems(self, texts: list[str]) -> None:
        # Çoklu model ekler / Adds multiple models
        self.set_models(texts)

    def clear(self) -> None:
        # Tüm modelleri ve arama kutusunu temizler / Clears all models and search input
        self._all_models.clear()
        self._search_input.clear()
        self._item_model.clear()
        self._model_combo.clear()

    def setEnabled(self, enabled: bool) -> None:
        # Bileşenin aktiflik durumunu ayarlar / Sets enabled state of component
        super().setEnabled(enabled)
        self._search_input.setEnabled(enabled)
        self._vendor_combo.setEnabled(enabled)
        self._model_combo.setEnabled(enabled)
