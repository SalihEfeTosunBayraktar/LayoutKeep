"""Widget tests for the provider settings dialog.

Keyring calls are monkeypatched to an in-memory dict so tests never touch the real OS
keychain, and no network call is made (the /v1/models fetch runs its own worker, which we
don't start in these tests).
"""

from __future__ import annotations

import pytest

from layoutkeep.ui import keyring_store
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.provider_settings import ProviderSettingsDialog


@pytest.fixture
def fake_keyring(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(keyring_store, "set_api_key", lambda url, key: store.__setitem__(url, key))
    monkeypatch.setattr(keyring_store, "get_api_key", lambda url: store.get(url))
    monkeypatch.setattr(keyring_store, "delete_api_key", lambda url: store.pop(url, None))
    return store


def test_api_key_field_is_optional(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://localhost:1234/v1"))
    qtbot.addWidget(dlg)

    assert dlg._api_key.text() == ""
    dlg._on_accept()

    config = dlg.result_config()
    assert config.api_key is None


def test_api_key_saved_to_keyring_not_returned_as_plain_dict(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://localhost:1234/v1"))
    qtbot.addWidget(dlg)

    dlg._api_key.setText("sk-secret")
    dlg._on_accept()

    assert fake_keyring["http://localhost:1234/v1"] == "sk-secret"
    assert dlg.result_config().api_key == "sk-secret"


def test_existing_key_prefilled_from_keyring(qtbot, fake_keyring):
    fake_keyring["http://localhost:1234/v1"] = "existing-key"
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://localhost:1234/v1"))
    qtbot.addWidget(dlg)

    assert dlg._api_key.text() == "existing-key"


def test_model_combo_prefilled_with_existing_model(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://x", model="llama-3"))
    qtbot.addWidget(dlg)

    assert dlg._model.currentText() == "llama-3"


def test_timeout_field_defaults_empty_meaning_adaptive(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://x"))
    qtbot.addWidget(dlg)

    assert dlg._timeout.text() == ""
    assert dlg.result_config().timeout is None


def test_timeout_field_round_trips_an_explicit_override(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://x", timeout=600.0))
    qtbot.addWidget(dlg)

    assert dlg._timeout.text() == "600.0"
    dlg._timeout.setText("120")
    assert dlg.result_config().timeout == 120.0


def test_timeout_field_invalid_input_falls_back_to_adaptive(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://x"))
    qtbot.addWidget(dlg)

    dlg._timeout.setText("not-a-number")
    assert dlg.result_config().timeout is None


def test_fake_provider_in_settings_dialog(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="fake", model="fake"))
    qtbot.addWidget(dlg)

    idx = dlg._kind_combo.findData("fake")
    assert idx >= 0
    dlg._kind_combo.setCurrentIndex(idx)

    assert dlg._base_url.isEnabled() is False
    assert dlg._model.isEnabled() is False
    assert dlg.result_config().kind == "fake"


def test_model_search_and_vendor_filtering_in_dialog(qtbot, fake_keyring):
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://x"))
    qtbot.addWidget(dlg)

    models = ["llama-3.2-3b", "qwen2.5-7b", "deepseek-r1:14b", "gpt-4o"]
    dlg._on_models(models)

    assert "4 model bulundu" in dlg._status.text()
    assert dlg._model.all_models() == models

    # Arama filtresi uygula
    dlg._model._search_input.setText("deepseek")
    assert dlg.result_config().model == "deepseek-r1:14b"



def test_deepl_profile_keeps_no_base_url_and_stores_its_key(qtbot, fake_keyring):
    """DeepL was selectable nowhere, and the two places that build a config from this dialog
    both hardcoded "openai" - so even once it was offered, choosing it produced an OpenAI job
    aimed at whatever URL the hidden box still held. It has no base URL of its own: the key
    decides the host."""
    dlg = ProviderSettingsDialog(ProviderConfig(kind="openai", base_url="http://localhost:1234/v1"))
    qtbot.addWidget(dlg)

    idx = dlg._kind_combo.findData("deepl")
    assert idx >= 0, "DeepL sağlayıcı türü listede yok"
    dlg._kind_combo.setCurrentIndex(idx)
    dlg._api_key.setText("key-1234:fx")

    config = dlg.result_config()
    assert config.kind == "deepl"
    assert config.base_url == ""

    dlg._form.profile_name.setText("DeepL testi")
    dlg._on_accept()

    # Keyed by kind, not by the empty base URL - otherwise every keyless provider shares one slot.
    assert fake_keyring["deepl"] == "key-1234:fx"

    from layoutkeep.ui.provider_profile import ProviderProfileStore

    saved = ProviderProfileStore().get_profile("DeepL testi")
    assert saved is not None
    assert saved.kind == "deepl"
    assert saved.base_url == ""
    assert saved.to_config().api_key == "key-1234:fx"
