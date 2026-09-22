"""Form alanları ile kayıtlı profil/ayar arasındaki bağ / Binding between the provider form and a profile.

Bu modül `ProviderSettingsForm`'un alanlarıyla kayıtlı bir profili ya da çalışan bir işin
ayarını eşler: hangi alanın hangi değeri taşıdığı ve sağlayıcı türü değiştiğinde hangi
alanın etkin/görünür kaldığı yalnız burada yazılır.

Kendi Qt durumunu tutmaz: her işlev formu parametre olarak alır, okur ve yazar.
"""

from __future__ import annotations

from layoutkeep.ui.api_key_helpers import keyring_id, load_api_key_for, save_api_key_for
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.provider_profile import ProviderProfile
from layoutkeep.ui.provider_settings_form import KIND_DEEPL, KIND_FAKE, KIND_OPENAI
from layoutkeep.ui.strings import UIStrings

KIND_FAKE_LABEL_FRAGMENT = UIStrings.PROVIDER_TEST_LABEL
FAKE_PROVIDER_MODEL = "fake"
DEFAULT_NEW_PROFILE_NAME = UIStrings.NEW_PROVIDER_LABEL
DEFAULT_NEW_BASE_URL = "http://127.0.0.1:1234/v1"
DEEPL_PROVIDER_DESCRIPTION = UIStrings.DEEPL_SELECTED_TOOLTIP
FAKE_PROVIDER_DESCRIPTION = UIStrings.TEST_SELECTED_TOOLTIP


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


def apply_kind_state(form) -> None:
    """Sağlayıcı türüne göre alanları etkinleştirir/gizler / Enables and hides per provider kind."""
    kind = form.kind_combo.currentData()
    is_fake = kind == KIND_FAKE
    is_deepl = kind == KIND_DEEPL
    form.base_url.setEnabled(not is_fake)
    form.model.setEnabled(not is_fake)
    form.refresh_btn.setEnabled(not is_fake)
    form.api_key.setEnabled(not is_fake)
    form.timeout.setEnabled(not is_fake)

    # DeepL takes neither of these. Leaving the boxes on screen with the previous profile's
    # localhost URL in them is how a DeepL profile ends up carrying a base URL that then
    # overrides the host the key belongs to.
    for widget in (form.base_url, form.model, form.refresh_btn):
        form.set_row_visible(widget, not is_deepl)
    form.api_key.setPlaceholderText(
        UIStrings.DEEPL_API_KEY_PLACEHOLDER
        if is_deepl
        else "opsiyonel - LM Studio/Ollama gerektirmez"
    )

    if is_fake:
        form.status.setText(FAKE_PROVIDER_DESCRIPTION)
    elif is_deepl:
        form.status.setText(DEEPL_PROVIDER_DESCRIPTION)
    elif (
        KIND_FAKE_LABEL_FRAGMENT in form.status.text()
        or form.status.text() == DEEPL_PROVIDER_DESCRIPTION
    ):
        form.status.clear()


def prefill_form(form, config: ProviderConfig) -> None:
    """Çalışan bir işin ayarını forma döker / Puts an existing configuration into the form."""
    idx_k = form.kind_combo.findData(config.kind)
    if idx_k >= 0:
        form.kind_combo.setCurrentIndex(idx_k)
    form.base_url.setText(config.base_url)
    form.api_key.setText(load_api_key_for(config.base_url))
    form.model.clear()
    if config.model:
        form.model.addItem(config.model)
        form.model.setEditText(config.model)
    form.timeout.setText(str(config.timeout) if config.timeout else "")
    apply_kind_state(form)


def apply_profile(form, profile: ProviderProfile) -> None:
    """Profil bilgilerini alanlara aktarır / Applies profile values to inputs."""
    form.profile_name.setText(profile.name)
    idx_kind = form.kind_combo.findData(profile.kind)
    if idx_kind >= 0:
        form.kind_combo.setCurrentIndex(idx_kind)
    form.base_url.setText(profile.base_url)
    form.model.clear()
    if profile.model:
        form.model.addItem(profile.model)
    form.api_key.setText(load_api_key_for(keyring_id(profile.kind, profile.base_url)))
    form.timeout.setText(str(profile.timeout) if profile.timeout else "")
    form.group.setCurrentText(profile.group)
    apply_kind_state(form)


def reset_for_new_profile(form) -> None:
    """Yeni uç nokta için alanları boşaltır / Clears the fields for a new endpoint."""
    form.endpoint_list.setCurrentItem(None)
    form.profile_name.setText(DEFAULT_NEW_PROFILE_NAME)
    form.profile_name.setFocus()
    form.profile_name.selectAll()
    form.base_url.setText(DEFAULT_NEW_BASE_URL)
    form.model.clear()
    form.api_key.clear()
    form.timeout.clear()


def profile_from_form(form) -> ProviderProfile:
    """Formdaki değerlerden profil üretir / Builds the profile the form currently describes."""
    kind = str(form.kind_combo.currentData() or KIND_OPENAI)
    prof_name = form.profile_name.text().strip() or UIStrings.CUSTOM_PROVIDER_FALLBACK
    if kind == KIND_FAKE:
        return ProviderProfile(
            name=prof_name,
            kind=KIND_FAKE,
            base_url="",
            model=FAKE_PROVIDER_MODEL,
            timeout=None,
            group=form.group.currentText().strip(),
        )

    # DeepL has no base URL or model of its own; storing whatever the boxes happened to
    # hold would send the job to a localhost server that is not DeepL.
    base_url = "" if kind == KIND_DEEPL else form.base_url.text().strip()
    model = "" if kind == KIND_DEEPL else form.model.currentText().strip()
    save_api_key_for(keyring_id(kind, base_url), form.api_key.text())
    return ProviderProfile(
        name=prof_name,
        kind=kind,
        base_url=base_url,
        model=model,
        timeout=parse_timeout(form.timeout.text()),
        group=form.group.currentText().strip(),
    )


def config_from_form(form) -> ProviderConfig:
    """Formdan çalıştırılacak ayarı üretir / Builds the ProviderConfig the form describes."""
    kind = str(form.kind_combo.currentData() or KIND_OPENAI)
    if kind == KIND_FAKE:
        return ProviderConfig(kind=KIND_FAKE, model=FAKE_PROVIDER_MODEL)

    # The kind was hardcoded here as well as in the save path, so a DeepL selection came
    # back out of the dialog as an OpenAI config pointed at whatever URL was in the box.
    base_url = "" if kind == KIND_DEEPL else form.base_url.text().strip()
    return ProviderConfig(
        kind=kind,
        base_url=base_url,
        model="" if kind == KIND_DEEPL else form.model.currentText().strip(),
        api_key=load_api_key_for(keyring_id(kind, base_url)) or None,
        timeout=parse_timeout(form.timeout.text()),
    )
