"""Job setup screen: pick a file, source/target language, format, provider, output path.

Girdi dosyası, kaynak/hedef dil, çıktı formatı ve sağlayıcı ayarlarını içeren kurulum ekranı.
Görsel katman mockup 03'e göredir: ikonlu kart başlıkları, ayarlar ızgarası ve play ikonlu
"Çeviriyi Başlat" butonu. İş mantığı (doğrulama, iş yayma, profil değişimi) JobSetupWidget'ta
ve testlerin bağlı olduğu attribute isimleri aynen korunur.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from layoutkeep.ui.drop_zone import DropZoneWidget
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.languages import LANGS, LanguageComboBox, definitions
from layoutkeep.ui.provider_combo import ProviderComboBox
from layoutkeep.ui.provider_profile import ProviderProfileStore
from layoutkeep.ui.provider_settings import ProviderSettingsDialog
from layoutkeep.ui.settings import app_settings
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

_LANGS = LANGS

#: Set this to put the test provider back in the list. It does not translate.
_DEV_PROVIDERS_ENV = "LAYOUTKEEP_DEV_PROVIDERS"

#: The format box holds a short phrase; the path box holds a path but not an essay.
_FORMAT_BOX_WIDTH = 260
_PATH_BOX_WIDTH = 520

#: Enough for the longest field label, and no more.
_LABEL_COLUMN_WIDTH = 26

#: A square-ish button for an icon with no text.
_ICON_BUTTON_WIDTH = 42
#: Evaluated once, at import, in whatever language was active then - which is why the box read
#: "Same as Source" in a Turkish window. `_format_choices()` reads the strings when they are
#: needed instead, and `retranslate_ui` refills the box.
_FORMAT_KEYS = [
    ("auto", "FORMAT_SAME"),
    (".pdf", "FORMAT_PDF"),
    (".html", "FORMAT_HTML"),
    (".epub", "FORMAT_EPUB"),
    (".docx", "FORMAT_DOCX"),
    (".png", "FORMAT_PNG"),
    (".jpg", "FORMAT_JPG"),
]


def _format_choices() -> list[tuple[str, str]]:
    # Cikti formati secenekleri, arayuz dilinde / Output format choices, in the interface language
    return [(ext, UIStrings.get(key)) for ext, key in _FORMAT_KEYS]


def _language_list() -> list[tuple[str, str]]:
    # Arayuz diline gore adlandirilmis dil listesi / The language list in the interface language
    return definitions(UIStrings.get_language())


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


class _JobSetupUiBuilder:
    """JobSetupWidget için görsel katman kurulumu.

    Tek sorumluluk: kurulum ekranının kontrollerini kurmak (girdi/çıktı alanları, dil
    seçicileri, sağlayıcı profili, düzen, sinyal bağları) ve arayüz metinlerini
    güncellemek. İş mantığı (doğrulama, iş yayma, profil değişimi) JobSetupWidget'ta kalır.
    """

    def _init_controls(self) -> None:
        # Form kontrollerini ilklendirir / Initializes form controls
        self._drop_zone = DropZoneWidget()
        self._input_path = QLineEdit()
        self._browse_in_btn = QPushButton(UIStrings.BROWSE_BTN)
        self._browse_in_btn.setIcon(get_svg_icon("folder", color=ThemeManager.current_palette().accent, size=16))

        self._output_path = QLineEdit()
        self._output_path.setMaximumWidth(_PATH_BOX_WIDTH)
        # Icon only. The word was there twice on one card, next to a field that says what it
        # opens; the folder mark carries it, and the tooltip spells it out for anyone unsure.
        self._browse_out_btn = QPushButton()
        self._browse_out_btn.setIcon(
            get_svg_icon("folder", color=ThemeManager.current_palette().accent, size=18)
        )
        self._browse_out_btn.setFixedWidth(_ICON_BUTTON_WIDTH)
        self._browse_out_btn.setToolTip(
            f"{UIStrings.BROWSE_BTN} - çıktı klasörünü seçin / Select output folder"
        )
        self._output_format = QComboBox()
        self._fill_format_combo()

        self._source_lang = LanguageComboBox()
        self._source_lang.populate(_language_list(), include_auto=True)
        self._target_lang = LanguageComboBox()
        self._target_lang.populate(_language_list(), include_auto=False)
        self._target_lang.setCurrentText("tr")

        self._range_mode = QComboBox()
        self._range_mode.addItem(UIStrings.RANGE_ALL, "all")
        self._range_mode.addItem(UIStrings.RANGE_CUSTOM, "custom")
        self._range_input = QLineEdit()
        self._range_input.setPlaceholderText(UIStrings.RANGE_PLACEHOLDER)
        self._range_input.hide()

        self._init_provider_controls()

    def _init_provider_controls(self) -> None:
        # Sağlayıcı ve profil kontrollerini kurar / Sets up provider and profile controls
        # There is deliberately no provider-kind dropdown here. There used to be one, but it
        # was never added to a layout - invisible, and yet it decided the kind of every job,
        # which is why DeepL could be chosen nowhere even though the provider was finished.
        # The profile now carries the kind, and the profile is what this screen selects.
        self._profile_store = ProviderProfileStore()
        self._provider_profile_combo = ProviderComboBox()
        self._refresh_profile_combo()

        active_prof = self._profile_store.get_profile(self._profile_store.get_active_profile_name())
        self._provider_config = active_prof.to_config() if active_prof else ProviderConfig(kind="openai")

        self._provider_btn = QPushButton()
        self._provider_btn.setIcon(
            get_svg_icon("sliders", color=ThemeManager.current_palette().accent, size=18)
        )
        self._provider_btn.setFixedWidth(_ICON_BUTTON_WIDTH)
        self._provider_btn.setToolTip(UIStrings.PROVIDER_SETTINGS_BTN)
        self._start_btn = QPushButton(UIStrings.START_TRANSLATION_BTN)
        self._start_btn.setProperty("class", "primary")
        self._start_btn.setIcon(get_svg_icon("play", color=ThemeManager.current_palette().accent_text, size=18))
        self._start_btn.setMinimumHeight(42)

    def _fill_format_combo(self) -> None:
        """(Re)fill the format box, keeping whatever was chosen."""
        chosen = self._output_format.currentData()
        self._output_format.blockSignals(True)
        self._output_format.clear()
        for ext, label in _format_choices():
            self._output_format.addItem(label, ext)
        if chosen is not None:
            index = self._output_format.findData(chosen)
            if index >= 0:
                self._output_format.setCurrentIndex(index)
        self._output_format.blockSignals(False)

    def _build_settings_card(self) -> SetupCard:
        # Ayarlar kartını ikonlu başlıkla kurar / Builds the icon-titled settings card
        # "Kaynak Dil:" and "Hedef Dil:" between two language boxes said what the arrow says.
        self._src_label = _icon_label("globe", UIStrings.SOURCE_LANG_LABEL)
        self._src_label.hide()
        self._tgt_label = _icon_label("arrow-right", UIStrings.TARGET_LANG_LABEL)
        langs_row = QHBoxLayout()
        langs_row.setSpacing(8)
        langs_row.addWidget(self._source_lang, 1)
        langs_row.addWidget(self._tgt_label)
        langs_row.addWidget(self._target_lang, 1)

        range_row = QHBoxLayout()
        range_row.addWidget(self._range_mode)
        range_row.addWidget(self._range_input)

        self._out_fmt_label = _icon_label("file-type", UIStrings.OUTPUT_FORMAT_LABEL)
        self._out_file_label = _icon_label("file-output", UIStrings.OUTPUT_FILE_LABEL)
        self._langs_label = _icon_label("globe", UIStrings.LANGS_LABEL)
        self._range_label = _icon_label("range", UIStrings.RANGE_LABEL)
        self._provider_label = _icon_label("server", UIStrings.PROVIDER_LABEL)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        # Spare width belongs to the fields. Without this the grid shares it out evenly and
        # the label column grew to a third of the card, holding two words.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnMinimumWidth(0, _LABEL_COLUMN_WIDTH)
        grid.addWidget(self._out_fmt_label, 0, 0)
        # No stretch and no second column: the longest entry here is a short phrase, and a
        # box the width of the card for it left the path below looking cramped by comparison.
        self._output_format.setMaximumWidth(_FORMAT_BOX_WIDTH)
        grid.addWidget(self._output_format, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(self._output_path)
        out_row.addWidget(self._browse_out_btn)
        out_row.addStretch()
        grid.addWidget(self._out_file_label, 1, 0)
        grid.addLayout(out_row, 1, 1, 1, 2)
        grid.addWidget(self._langs_label, 2, 0)
        grid.addLayout(langs_row, 2, 1, 1, 2)
        grid.addWidget(self._range_label, 3, 0)
        grid.addLayout(range_row, 3, 1, 1, 2)
        grid.addWidget(self._provider_label, 4, 0)
        grid.addWidget(self._provider_profile_combo, 4, 1)
        grid.addWidget(self._provider_btn, 4, 2)

        card = SetupCard("settings", UIStrings.SETTINGS_CARD_TITLE)
        card.add_body(grid)
        return card

    def _build_layout(self) -> None:
        # Arayüz düzenini mockup 03'e göre kurar / Builds the mockup-03 style layout
        card = self._build_settings_card()

        self._cards = [card]

        # The drop zone and the settings card scroll together; the start button stays put at
        # the bottom, where it has to be reachable at any window size.
        scrolled = QWidget()
        scrolled.setObjectName("scrollPage")
        inner = QVBoxLayout(scrolled)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(12)
        # No stretch: the drop zone takes what it needs and the space goes to the settings
        # card, which has something in it to read.
        inner.addWidget(self._drop_zone)
        inner.addWidget(card)
        inner.addStretch(1)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(scrolled)
        scroller.viewport().setAutoFillBackground(False)
        scrolled.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(scroller, 1)
        layout.addWidget(self._start_btn)
        layout.addStretch()

    def retranslate_ui(self) -> None:
        # Arayüz diline göre metinleri günceller / Updates texts for active language
        # So are the format names, which were read once at import and then never again.
        self._fill_format_combo()
        # The language names are translations too, so the pickers are refilled rather than
        # left reading "Türkçe" in an English window.
        self._apply_provider_language_limits()

        # The row markers are drawn, so what changes with the language is their tooltip.
        for label, text in (
            (self._src_label, UIStrings.SOURCE_LANG_LABEL),
            (self._tgt_label, f"{UIStrings.SOURCE_LANG_LABEL} \u2192 {UIStrings.TARGET_LANG_LABEL}"),
            (self._out_fmt_label, UIStrings.OUTPUT_FORMAT_LABEL),
            (self._out_file_label, UIStrings.OUTPUT_FILE_LABEL),
            (self._langs_label, UIStrings.LANGS_LABEL),
            (self._range_label, UIStrings.RANGE_LABEL),
            (self._provider_label, UIStrings.PROVIDER_LABEL),
        ):
            label.setToolTip(text)
        self._browse_in_btn.setText(UIStrings.BROWSE_BTN)
        # Icon only - retranslating put the word back and it did not fit the narrow button.
        self._browse_out_btn.setToolTip(
            f"{UIStrings.BROWSE_BTN} - çıktı klasörünü seçin / Select output folder"
        )
        self._provider_btn.setToolTip(UIStrings.PROVIDER_SETTINGS_BTN)
        self._start_btn.setText(UIStrings.START_TRANSLATION_BTN)
        self._range_input.setPlaceholderText(UIStrings.RANGE_PLACEHOLDER)
        self._range_mode.setItemText(0, UIStrings.RANGE_ALL)
        self._range_mode.setItemText(1, UIStrings.RANGE_CUSTOM)
        self._drop_zone.retranslate_ui()
        for card in getattr(self, "_cards", []):
            if isinstance(card, SetupCard):
                card.retitle(UIStrings.SETTINGS_CARD_TITLE)

    def apply_theme(self) -> None:
        # Tema değişiminde kart ve buton ikonlarını tazeler / Refreshes card and button icons
        pal = ThemeManager.current_palette()
        for card in getattr(self, "_cards", []):
            card.apply_theme()
        self._start_btn.setIcon(get_svg_icon("play", color=pal.accent_text, size=18))
        self._browse_in_btn.setIcon(get_svg_icon("folder", color=pal.accent, size=16))
        self._drop_zone.apply_theme()

    def _refresh_profile_combo(self) -> None:
        # Saglayicilari klasorlu ve sirali listeler / Lists providers as folders, in order
        profiles = self._profile_store.list_profiles()
        if not os.environ.get(_DEV_PROVIDERS_ENV):
            # The test provider does not translate - it prefixes the source with a language
            # tag - so its output looks like a broken translation rather than a test fixture.
            # It stays available to development runs through the environment variable.
            profiles = [p for p in profiles if p.kind != "fake"]

        combo = self._provider_profile_combo
        combo.blockSignals(True)
        combo.populate(profiles, self._profile_store.get_active_profile_name())
        combo.blockSignals(False)
        self._on_profile_changed()

    def _connect_signals(self) -> None:
        # Kontrol sinyallerini bağlar / Connects control signals
        self._drop_zone.file_selected.connect(self._on_drop_file)
        self._input_path.textChanged.connect(self._on_input_text_changed)
        self._browse_in_btn.clicked.connect(self._browse_input)
        self._browse_out_btn.clicked.connect(self._browse_output)
        self._output_format.currentIndexChanged.connect(self._on_format_changed)
        self._range_mode.currentIndexChanged.connect(self._on_range_mode_changed)
        self._source_lang.currentTextChanged.connect(self._on_source_lang_changed)
        self._target_lang.currentTextChanged.connect(self._on_target_lang_changed)
        self._provider_profile_combo.lineEdit().textChanged.connect(self._on_profile_changed)
        self._provider_btn.clicked.connect(self._open_provider_settings)
        self._start_btn.clicked.connect(self._emit_job)


class JobSetupWidget(_JobSetupUiBuilder, QWidget):
    # Çeviri işi ayarlarını toplayıp job_ready sinyali yayan bileşen / Job setup widget
    job_ready = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings = app_settings()
        self._init_controls()
        self._build_layout()
        self._connect_signals()
        self._load_saved_settings()

    def _on_source_lang_changed(self, _text: str) -> None:
        # Kaynak dil tercihini anında kalıcı kaydeder / Saves source language preference immediately
        code = self._source_lang.currentText()
        if code:
            self._settings.setValue("source_lang", code)

    def _on_target_lang_changed(self, _text: str) -> None:
        # Hedef dil tercihini anında kalıcı kaydeder / Saves target language preference immediately
        code = self._target_lang.currentText()
        if code:
            self._settings.setValue("target_lang", code)

    def _on_input_text_changed(self, text: str) -> None:
        # Input path dışarıdan değişirse dropzone ve çıktıyı senkronize eder / Syncs dropzone on path change
        if text and self._drop_zone._current_path != text:
            self._drop_zone.set_file_path(text)
        if text and not self._output_path.text():
            self._update_output_path(text)

    def _on_profile_changed(self) -> None:
        # Seçilen profili aktife alır ve ayarı kalıcı kaydeder / Activates and persists profile
        prof = self._provider_profile_combo.current_profile()
        if prof is not None and hasattr(prof, "to_config"):
            self._provider_config = prof.to_config()
            self._profile_store.set_active_profile_name(prof.name)
        self._apply_provider_language_limits()

    def _apply_provider_language_limits(self) -> None:
        """Offer only the languages the selected provider can actually translate.

        DeepL answers HTTP 400 for anything outside its own list and the whole job fails, so
        offering Persian next to French is offering a choice that cannot work. A local model
        will attempt any pair, well or badly, so nothing is narrowed there.
        """
        from layoutkeep.providers.deepl import SUPPORTED_LANGUAGES

        kind = getattr(self._provider_config, "kind", None)
        available = (
            [pair for pair in _language_list() if pair[0] in SUPPORTED_LANGUAGES]
            if kind == "deepl"
            else _language_list()
        )
        for combo, include_auto, fallback in (
            (self._source_lang, True, "auto"),
            (self._target_lang, False, "tr"),
        ):
            previous = combo.currentText()
            combo.populate(available, include_auto=include_auto)
            # Keep the user's choice when the narrower list still has it; a silent switch to
            # another language would be worse than the error we are avoiding.
            combo.setCurrentText(previous if combo.findText(previous) >= 0 else fallback)

    def _on_drop_file(self, path: str) -> None:
        # Sürüklenen dosyayı girdi kutusuna aktarır / Sets dropped file to input line
        self._input_path.setText(path)
        if path:
            self._update_output_path(path)

    def _update_output_path(self, in_path: str) -> None:
        # Çıktı yolunu kayıtlı klasöre ve formata göre günceller / Updates output path based on folder and format
        src = Path(in_path)
        selected_ext = self._output_format.currentData()
        target_ext = src.suffix if selected_ext == "auto" else selected_ext
        saved_dir = str(self._settings.value("output_folder", ""))
        out_dir = Path(saved_dir) if saved_dir and Path(saved_dir).exists() else src.parent
        self._output_path.setText(str(out_dir / f"{src.stem}.out{target_ext}"))

    def _on_format_changed(self) -> None:
        # Format seçimi değiştiğinde tercihi kaydeder ve çıktıyı günceller / Saves format and updates output
        fmt = self._output_format.currentData()
        if fmt:
            self._settings.setValue("output_format", str(fmt))
        in_path = self._input_path.text().strip()
        if in_path:
            self._update_output_path(in_path)

    def _browse_input(self) -> None:
        # Girdi dosyası seçme diyaloğu / Input file open dialog
        filters = (
            "Tüm Desteklenen Belgeler (*.epub *.pdf *.docx *.png *.jpg *.jpeg *.webp *.bmp *.tiff *.lkproj);;"
            "Belgeler (*.epub *.pdf *.docx *.lkproj);;Görseller (*.png *.jpg *.jpeg *.webp *.bmp *.tiff)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Belge Seç", "", filters)
        if path:
            self._input_path.setText(path)
            self._drop_zone.set_file_path(path)
            if not self._output_path.text() or ".out" in self._output_path.text():
                self._update_output_path(path)

    def _browse_output(self) -> None:
        # Çıktı klasörünü seçtirir ve kalıcı olarak kaydeder / Selects and persists output folder
        saved_dir = str(self._settings.value("output_folder", ""))
        initial_dir = saved_dir if saved_dir and Path(saved_dir).exists() else ""
        if not initial_dir and self._input_path.text().strip():
            src_parent = str(Path(self._input_path.text().strip()).parent)
            if Path(src_parent).exists():
                initial_dir = src_parent

        folder = QFileDialog.getExistingDirectory(self, "Çıktı Klasörünü Seç", initial_dir)
        if folder:
            self._settings.setValue("output_folder", folder)
            in_path = self._input_path.text().strip()
            if in_path:
                self._update_output_path(in_path)
            else:
                self._output_path.setText(folder)

    def _open_provider_settings(self) -> None:
        dlg = ProviderSettingsDialog(self._provider_config, self)
        if dlg.exec():
            self._provider_config = dlg.result_config()
            self._refresh_profile_combo()

    def _load_saved_settings(self) -> None:
        # Kaydedilmiş dil ve sağlayıcı tercihlerini geri yükler / Restores saved preferences
        saved_source = str(self._settings.value("source_lang", "auto"))
        self._source_lang.setCurrentText(saved_source)

        saved_target = str(self._settings.value("target_lang", "tr"))
        self._target_lang.setCurrentText(saved_target)

        saved_folder = str(self._settings.value("output_folder", ""))
        if saved_folder and Path(saved_folder).exists():
            self._output_path.setPlaceholderText(f"Varsayılan Klasör: {saved_folder}")

    def _on_range_mode_changed(self, index: int) -> None:
        # Aralık modu değiştiğinde özel aralık kutusunu gösterir/gizler / Shows/hides custom range input
        self._range_input.setVisible(index == 1)

    def _emit_job(self) -> None:
        # Doğrulamadan sonra job_ready sinyali yayar / Validates and emits job_ready signal
        kind = getattr(self._provider_config, "kind", None) or "openai"
        is_fake = kind == "fake"
        if is_fake:
            provider = ProviderConfig(kind="fake", model="fake")
        else:
            provider = replace(self._provider_config, kind=kind)
        error = self._validation_error(kind)
        if error is not None:
            QMessageBox.warning(self, UIStrings.ERR_INCOMPLETE_INFO, error)
            return

        self._settings.setValue("target_lang", self._target_lang.currentText())
        page_range = self._range_input.text().strip() if self._range_mode.currentIndex() == 1 else ""

        output_str = self._output_path.text().strip()
        input_str = self._input_path.text().strip()
        if output_str and Path(output_str).is_dir() and input_str:
            src = Path(input_str)
            selected_ext = self._output_format.currentData()
            target_ext = src.suffix if selected_ext == "auto" else selected_ext
            output_str = str(Path(output_str) / f"{src.stem}.out{target_ext}")
            self._output_path.setText(output_str)

        config = JobConfig(
            input_path=input_str,
            output_path=output_str,
            source_lang=self._source_lang.currentText(),
            target_lang=self._target_lang.currentText(),
            provider=provider,
            page_range=page_range,
        )
        self.job_ready.emit(config)

    def _validation_error(self, provider_kind: str) -> str | None:
        # Form alanlarının geçerliliğini denetler / Validates form field values
        input_path = self._input_path.text().strip()
        if not input_path:
            return UIStrings.ERR_MISSING_INPUT
        if not Path(input_path).exists():
            return f"{UIStrings.ERR_INPUT_NOT_FOUND}{input_path}"

        output_path = self._output_path.text().strip()
        if not output_path:
            return UIStrings.ERR_MISSING_OUTPUT
        if Path(output_path).is_dir():
            if not Path(output_path).exists():
                return f"{UIStrings.ERR_OUTPUT_DIR_NOT_FOUND}{output_path}"
        elif not Path(output_path).parent.exists():
            return f"{UIStrings.ERR_OUTPUT_DIR_NOT_FOUND}{Path(output_path).parent}"

        if provider_kind == "openai" and not self._provider_config.model.strip():
            return UIStrings.ERR_NO_MODEL
        if provider_kind == "deepl" and not (self._provider_config.api_key or "").strip():
            # DeepL has no model to pick; without a key there is nothing to send.
            return UIStrings.ERR_NO_API_KEY
        return None
