"""Provider settings dialog: manages multiple provider profiles (base URL, model, API key).

Birden fazla sağlayıcı profilini listeleme, ekleme, düzenleme ve seçme işlemlerini yöneten ayar diyaloğu.

Form alanlarıyla profil/ayar eşlemesi `provider_form_binding` modülünde; bu dosya uç nokta
listesini, kaydetme/silme akışını ve model/bağlantı sorgularını yönetir.
"""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMenu

from layoutkeep.ui.connection_test_worker import ConnectionTestWorker
from layoutkeep.ui.endpoint_tree import PROFILE_ROLE, EndpointTree
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.list_models_worker import ListModelsWorker
from layoutkeep.ui.provider_form_binding import (
    FAKE_PROVIDER_DESCRIPTION,
    apply_kind_state,
    apply_profile,
    config_from_form,
    parse_timeout,
    prefill_form,
    profile_from_form,
    reset_for_new_profile,
)
from layoutkeep.ui.provider_profile import ProviderProfile, ProviderProfileStore
from layoutkeep.ui.provider_settings_form import (
    KIND_DEEPL,
    KIND_FAKE,
    KIND_OPENAI,
    ProviderSettingsForm,
)
from layoutkeep.ui.strings import UIStrings


def _endpoint_summary(profile: ProviderProfile) -> str:
    # Listede fare ustundeyken gosterilen ozet / Summary shown on hover in the list
    if profile.kind == KIND_DEEPL:
        return "DeepL - anahtar sunucuyu belirler"
    if profile.kind == KIND_FAKE:
        return FAKE_PROVIDER_DESCRIPTION
    return f"{profile.base_url} - {profile.model or 'model secilmedi'}"


class ProviderSettingsDialog(QDialog):
    # Çoklu sağlayıcı profillerini yöneten ayar penceresi / Dialog managing multiple provider profiles

    def __init__(self, config: ProviderConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(UIStrings.PROVIDER_SETTINGS_TITLE)
        self._store = ProviderProfileStore()
        cfg = config or ProviderConfig(kind=KIND_OPENAI)
        self._form = ProviderSettingsForm(self, cfg)
        self._list_worker: ListModelsWorker | None = None
        self._connect_signals()
        self._load_profiles_into_ui()
        self._fit_to_screen()
        if config is not None:
            prefill_form(self._form, config)

    def _fit_to_screen(self) -> None:
        """Open at a size that leaves the buttons on the screen.

        A dialog taller than the display puts its own Save and Cancel below the bottom edge,
        where no amount of scrolling inside it helps.
        """
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        width, height = 600, 640
        if available is not None:
            width = min(width, int(available.width() * 0.9))
            height = min(height, int(available.height() * 0.85))
        self.resize(width, height)

    # ------------------------------------------------------------------ init
    def _connect_signals(self) -> None:
        # Olay bağlantılarını kurar / Sets up signal connections
        f = self._form
        f.refresh_btn.clicked.connect(self._fetch_models)
        f.endpoint_list.currentItemChanged.connect(self._on_endpoint_selected)
        f.endpoint_list.arrangement_changed.connect(self._on_arrangement_changed)
        f.endpoint_list.customContextMenuRequested.connect(self._show_endpoint_menu)
        f.new_profile_btn.clicked.connect(lambda: reset_for_new_profile(f))
        f.test_btn.clicked.connect(self._test_connection)
        f.save_btn.clicked.connect(self._save_endpoint)
        # The combo hands the new index to the slot; the kind state is read from the form.
        f.kind_combo.currentIndexChanged.connect(lambda *_: apply_kind_state(f))
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
            apply_profile(self._form, current)

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
            apply_profile(self._form, profile)

    def _save_endpoint(self) -> None:
        """Store the form as an endpoint without closing the dialog.

        Adding several endpoints in one visit is the normal case, and a dialog that closes on
        every save turns that into one trip each.
        """
        profile = profile_from_form(self._form)
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

    # ----------------------------------------------------------------- models
    def _fetch_models(self) -> None:
        # Model listesini sunucudan getirir / Fetches model list from provider
        f = self._form
        f.refresh_btn.setEnabled(False)
        f.status.setText(UIStrings.STATUS_FETCHING_MODELS)
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
            self._form.status.setText(UIStrings.MODELS_FOUND_STATUS.format(len(models)))
        else:
            self._form.status.setText(UIStrings.STATUS_NO_MODELS)

    def _on_models_failed(self, message: str) -> None:
        self._form.status.setText(
            UIStrings.SERVER_UNREACHABLE_STATUS.format(message)
            + "\n"
            + UIStrings.SERVER_UNREACHABLE_HINT.format("")
        )

    # ------------------------------------------------------------- save/result
    def _on_accept(self) -> None:
        # Ayarları kaydeder ve profili günceller / Saves settings and profile
        profile = profile_from_form(self._form)
        self._store.upsert_profile(profile)
        self.accept()

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
        return config_from_form(self._form)
