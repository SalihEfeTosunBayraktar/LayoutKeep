"""Provider settings dialog: manages multiple provider profiles (base URL, model, API key).

Birden fazla sağlayıcı profilini listeleme, ekleme, düzenleme ve seçme işlemlerini yöneten ayar diyaloğu.
"""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMenu

from layoutkeep.ui.api_key_helpers import keyring_id, load_api_key_for, save_api_key_for
from layoutkeep.ui.connection_test_worker import ConnectionTestWorker
from layoutkeep.ui.endpoint_tree import PROFILE_ROLE, EndpointTree
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.list_models_worker import ListModelsWorker
from layoutkeep.ui.provider_profile import ProviderProfile, ProviderProfileStore
from layoutkeep.ui.provider_settings_form import (
    KIND_DEEPL,
    KIND_FAKE,
    KIND_OPENAI,
    ProviderSettingsForm,
)
from layoutkeep.ui.strings import UIStrings

_KIND_FAKE_LABEL_FRAGMENT = "Test / Sahte Çevirici"
_FAKE_PROVIDER_MODEL = "fake"
_DEFAULT_NEW_PROFILE_NAME = "Yeni Sağlayıcı"
_DEFAULT_NEW_BASE_URL = "http://localhost:1234/v1"
_DEEPL_PROVIDER_DESCRIPTION = (
    "DeepL seçili. Base URL ve model gerekmez; anahtar hangi sunucuya gidileceğini "
    "kendisi belirler - ücretsiz anahtarlar ':fx' ile biter ve api-free.deepl.com "
    "adresine gider. API anahtarı zorunludur."
)
_FAKE_PROVIDER_DESCRIPTION = (
    "Test / Sahte Çevirici etkindir. Kelimelerin/cümlelerin başına seçilen dil etiketini "
    "(örn. [tr]) ekler; yerel veya uzak sunucu gerektirmez."
)


def parse_timeout(raw: str) -> float | None:
    """Parse a free-form timeout field into a float; return None on empty / invalid.

    Serbest biçimli zaman aşımı alanını float'a çevirir; boş/geçersiz ise None döner.
    """
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _endpoint_summary(profile: ProviderProfile) -> str:
    # Listede fare ustundeyken gosterilen ozet / Summary shown on hover in the list
    if profile.kind == KIND_DEEPL:
        return "DeepL - anahtar sunucuyu belirler"
    if profile.kind == KIND_FAKE:
        return _FAKE_PROVIDER_DESCRIPTION
    return f"{profile.base_url} - {profile.model or 'model secilmedi'}"


class ProviderSettingsDialog(QDialog):
    # Çoklu sağlayıcı profillerini yöneten ayar penceresi / Dialog managing multiple provider profiles

    def __init__(self, config: ProviderConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sağlayıcı Ayarları")
        self._store = ProviderProfileStore()
        cfg = config or ProviderConfig(kind=KIND_OPENAI)
        self._form = ProviderSettingsForm(self, cfg)
        self._list_worker: ListModelsWorker | None = None
        self._connect_signals()
        self._load_profiles_into_ui()
        self._fit_to_screen()
        if config is not None:
            self._prefill_from_config(config)

    def _fit_to_screen(self) -> None:
        """Open at a size that leaves the buttons on the screen.

        A dialog taller than the display puts its own Save and Cancel below the bottom edge,
        where no amount of scrolling inside it helps.
        """
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width, height = 600, 560
        if available is not None:
            width = min(width, int(available.width() * 0.9))
            height = min(height, int(available.height() * 0.85))
        self.resize(width, height)

    # ------------------------------------------------------------------ init
    def _prefill_from_config(self, config: ProviderConfig) -> None:
        idx_k = self._form.kind_combo.findData(config.kind)
        if idx_k >= 0:
            self._form.kind_combo.setCurrentIndex(idx_k)
        self._form.base_url.setText(config.base_url)
        self._form.api_key.setText(load_api_key_for(config.base_url))
        self._form.model.clear()
        if config.model:
            self._form.model.addItem(config.model)
            self._form.model.setEditText(config.model)
        self._form.timeout.setText(str(config.timeout) if config.timeout else "")
        self._on_kind_changed()

    def _connect_signals(self) -> None:
        # Olay bağlantılarını kurar / Sets up signal connections
        f = self._form
        f.refresh_btn.clicked.connect(self._fetch_models)
        f.endpoint_list.currentItemChanged.connect(self._on_endpoint_selected)
        f.endpoint_list.arrangement_changed.connect(self._on_arrangement_changed)
        f.endpoint_list.customContextMenuRequested.connect(self._show_endpoint_menu)
        f.new_profile_btn.clicked.connect(self._init_new_profile_fields)
        f.test_btn.clicked.connect(self._test_connection)
        f.save_btn.clicked.connect(self._save_endpoint)
        f.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        f.buttons.accepted.connect(self._on_accept)
        f.buttons.rejected.connect(self.reject)

    # --------------------------------------------------------------- profiles
    def _load_profiles_into_ui(self, select_name: str | None = None) -> None:
        # Kayitli uc noktalari klasor agacinda gosterir / Shows saved endpoints as a tree
        tree = self._form.endpoint_list
        tree.load(
            self._store.list_profiles(),
            select_name or self._store.get_active_profile_name(),
        )
        self._refresh_group_choices()
        current = self._selected_profile()
        if current is not None:
            self._apply_profile(current)

    def _on_arrangement_changed(self, profiles: list[ProviderProfile]) -> None:
        """The tree is the arrangement; storing it is all that is left to do."""
        self._store.save_profiles(profiles)
        self._refresh_group_choices()

    def _show_endpoint_menu(self, point) -> None:
        # Sag tik menusu / Right-click menu on the tree
        tree: EndpointTree = self._form.endpoint_list
        item = tree.itemAt(point)
        if item is None:
            return
        tree.setCurrentItem(item)
        menu = self.build_endpoint_menu(item)
        if menu is not None:
            menu.exec(tree.viewport().mapToGlobal(point))

    def build_endpoint_menu(self, item) -> QMenu | None:
        """The menu for one row, built but not shown.

        Actions are created and connected rather than passed to `addAction(text, callable)`:
        that call has a sibling overload taking a receiver and a slot name, and handing it a
        bound method of a QObject picks the wrong one - it looks for a Qt slot that does not
        exist and raises. A packaged run's crash log carried exactly that, which meant the
        only way to delete or rename an endpoint did not open at all.
        """
        tree: EndpointTree = self._form.endpoint_list
        profile = item.data(0, PROFILE_ROLE)
        menu = QMenu(self)

        def add(text: str, handler) -> None:
            action = QAction(text, menu)
            action.triggered.connect(lambda _checked=False, run=handler: run())
            menu.addAction(action)

        if profile is None:
            add(UIStrings.MENU_RENAME_GROUP, lambda: tree.rename_group(item))
            add(UIStrings.MENU_UNGROUP_ALL, lambda: tree.ungroup(item))
        else:
            add(UIStrings.MENU_TEST_CONNECTION, self._test_connection)
            if item.parent() is not None:
                add(UIStrings.MENU_LEAVE_GROUP, lambda: tree.ungroup(item))
            menu.addSeparator()
            add(UIStrings.MENU_DELETE, lambda: self._delete_endpoint(profile.name))
        return menu

    def _delete_endpoint(self, name: str) -> None:
        self._store.delete_profile(name)
        self._load_profiles_into_ui()

    def _selected_profile(self) -> ProviderProfile | None:
        return self._form.endpoint_list.selected_profile()

    def _refresh_group_choices(self) -> None:
        # Var olan gruplari onerir, yazilani korur / Offers existing groups, keeps typed text
        combo = self._form.group
        typed = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        for name in self._store.groups():
            combo.addItem(name)
        combo.setCurrentText(typed)
        combo.blockSignals(False)

    def _on_endpoint_selected(self, _current=None, _previous=None) -> None:
        # Listeden uc nokta secildiginde alanlari doldurur / Fills the form on selection
        profile = self._selected_profile()
        if profile is not None:
            self._apply_profile(profile)

    def _save_endpoint(self) -> None:
        """Store the form as an endpoint without closing the dialog.

        Adding several endpoints in one visit is the normal case, and a dialog that closes on
        every save turns that into one trip each.
        """
        profile = self._build_profile_from_form()
        self._store.upsert_profile(profile)
        self._load_profiles_into_ui(select_name=profile.name)
        self._form.status.setText(f"{profile.name} kaydedildi.")

    def _test_connection(self) -> None:
        # Uc noktayi kaydetmeden sinar / Tests the endpoint without saving it
        f = self._form
        kind = str(f.kind_combo.currentData() or KIND_OPENAI)
        f.test_btn.setEnabled(False)
        f.status.setText("baglanti sinaniyor...")
        self._test_worker = ConnectionTestWorker(
            kind,
            "" if kind == KIND_DEEPL else f.base_url.text().strip(),
            f.api_key.text() or None,
            parse_timeout(f.timeout.text()),
        )
        self._test_worker.succeeded.connect(f.status.setText)
        self._test_worker.failed.connect(lambda msg: f.status.setText(f"Basarisiz: {msg}"))
        self._test_worker.finished.connect(lambda: f.test_btn.setEnabled(True))
        self._test_worker.start()

    def _init_new_profile_fields(self) -> None:
        f = self._form
        f.endpoint_list.setCurrentItem(None)
        f.profile_name.setText(_DEFAULT_NEW_PROFILE_NAME)
        f.profile_name.setFocus()
        f.profile_name.selectAll()
        f.base_url.setText(_DEFAULT_NEW_BASE_URL)
        f.model.clear()
        f.api_key.clear()
        f.timeout.clear()

    def _apply_profile(self, profile: ProviderProfile) -> None:
        # Profil bilgilerini alanlara aktarır / Applies profile values to inputs
        f = self._form
        f.profile_name.setText(profile.name)
        idx_kind = f.kind_combo.findData(profile.kind)
        if idx_kind >= 0:
            f.kind_combo.setCurrentIndex(idx_kind)
        f.base_url.setText(profile.base_url)
        f.model.clear()
        if profile.model:
            f.model.addItem(profile.model)
        f.api_key.setText(load_api_key_for(keyring_id(profile.kind, profile.base_url)))
        f.timeout.setText(str(profile.timeout) if profile.timeout else "")
        f.group.setCurrentText(profile.group)
        self._on_kind_changed()

    # --------------------------------------------------------------- kind UI
    def _on_kind_changed(self) -> None:
        # Sağlayıcı türü değiştiğinde ilgili alanları etkinleştirir/devre dışı bırakır / Handles provider type change
        f = self._form
        kind = f.kind_combo.currentData()
        is_fake = kind == KIND_FAKE
        is_deepl = kind == KIND_DEEPL
        f.base_url.setEnabled(not is_fake)
        f.model.setEnabled(not is_fake)
        f.refresh_btn.setEnabled(not is_fake)
        f.api_key.setEnabled(not is_fake)
        f.timeout.setEnabled(not is_fake)

        # DeepL takes neither of these. Leaving the boxes on screen with the previous profile's
        # localhost URL in them is how a DeepL profile ends up carrying a base URL that then
        # overrides the host the key belongs to.
        for widget in (f.base_url, f.model, f.refresh_btn):
            f.set_row_visible(widget, not is_deepl)
        f.api_key.setPlaceholderText(
            "zorunlu - DeepL anahtarı (ücretsiz anahtarlar ':fx' ile biter)"
            if is_deepl
            else "opsiyonel - LM Studio/Ollama gerektirmez"
        )

        if is_fake:
            f.status.setText(_FAKE_PROVIDER_DESCRIPTION)
        elif is_deepl:
            f.status.setText(_DEEPL_PROVIDER_DESCRIPTION)
        elif _KIND_FAKE_LABEL_FRAGMENT in f.status.text() or f.status.text() == _DEEPL_PROVIDER_DESCRIPTION:
            f.status.clear()

    # ----------------------------------------------------------------- models
    def _fetch_models(self) -> None:
        # Model listesini sunucudan getirir / Fetches model list from provider
        f = self._form
        f.refresh_btn.setEnabled(False)
        f.status.setText("modeller alınıyor...")
        self._list_worker = ListModelsWorker(f.base_url.text().strip(), f.api_key.text() or None)
        self._list_worker.succeeded.connect(self._on_models)
        self._list_worker.failed.connect(self._on_models_failed)
        self._list_worker.finished.connect(lambda: f.refresh_btn.setEnabled(True))
        self._list_worker.start()

    def _on_models(self, models: list[str]) -> None:
        current = self._form.model.currentText()
        self._form.model.set_models(models)
        if current:
            self._form.model.setEditText(current)
        if models:
            self._form.status.setText(f"{len(models)} model bulundu (üreticilere göre gruplandı)")
        else:
            self._form.status.setText("sunucu model döndürmedi")

    def _on_models_failed(self, message: str) -> None:
        self._form.status.setText(
            f"Sunucuya ulaşılamadı: {message}\n"
            "LM Studio veya Ollama sunucusunun çalıştığından emin olun."
        )

    # ------------------------------------------------------------- save/result
    def _on_accept(self) -> None:
        # Ayarları kaydeder ve profili günceller / Saves settings and profile
        profile = self._build_profile_from_form()
        self._store.upsert_profile(profile)
        self.accept()

    def _build_profile_from_form(self) -> ProviderProfile:
        f = self._form
        kind = str(f.kind_combo.currentData() or KIND_OPENAI)
        prof_name = f.profile_name.text().strip() or "Özel Sağlayıcı"
        if kind == KIND_FAKE:
            return ProviderProfile(
                name=prof_name,
                kind=KIND_FAKE,
                base_url="",
                model=_FAKE_PROVIDER_MODEL,
                timeout=None,
                group=f.group.currentText().strip(),
            )

        # DeepL has no base URL or model of its own; storing whatever the boxes happened to
        # hold would send the job to a localhost server that is not DeepL.
        base_url = "" if kind == KIND_DEEPL else f.base_url.text().strip()
        model = "" if kind == KIND_DEEPL else f.model.currentText().strip()
        save_api_key_for(keyring_id(kind, base_url), f.api_key.text())
        return ProviderProfile(
            name=prof_name,
            kind=kind,
            base_url=base_url,
            model=model,
            timeout=parse_timeout(f.timeout.text()),
            group=f.group.currentText().strip(),
        )

    # Eski test/dış erişim uyumluluğu: form bileşenlerine kısa yol (önceden düz öznitelikti)
    _LEGACY_FORM_ATTRS = frozenset(
        {"_kind_combo", "_base_url", "_api_key", "_model", "_timeout", "_status"}
    )

    def __getattr__(self, name: str):
        if name in self._LEGACY_FORM_ATTRS:
            return getattr(self._form, name[1:])
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def result_config(self) -> ProviderConfig:
        # Sonuç ProviderConfig nesnesini döndürür / Returns resulting ProviderConfig
        f = self._form
        kind = str(f.kind_combo.currentData() or KIND_OPENAI)
        if kind == KIND_FAKE:
            return ProviderConfig(kind=KIND_FAKE, model=_FAKE_PROVIDER_MODEL)

        # The kind was hardcoded here as well as in the save path, so a DeepL selection came
        # back out of the dialog as an OpenAI config pointed at whatever URL was in the box.
        base_url = "" if kind == KIND_DEEPL else f.base_url.text().strip()
        return ProviderConfig(
            kind=kind,
            base_url=base_url,
            model="" if kind == KIND_DEEPL else f.model.currentText().strip(),
            api_key=load_api_key_for(keyring_id(kind, base_url)) or None,
            timeout=parse_timeout(f.timeout.text()),
        )
