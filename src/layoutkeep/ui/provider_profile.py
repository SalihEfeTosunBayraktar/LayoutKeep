"""Provider profile manager: stores, retrieves, and persists multiple provider configurations.

Birden fazla çeviri sağlayıcısı profilini kalıcı saklayan, listeleyen ve yöneten profil deposu.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.settings import app_settings

_SETTINGS_KEY_PROFILES = "provider_profiles_v1"
_SETTINGS_KEY_ACTIVE = "active_provider_profile"

#: DeepL needs no base URL and has no model to choose - the key decides the host - so the
#: profile carries nothing but its kind until the user pastes a key into it.
_DEEPL_PROFILE = {
    "name": "DeepL (API anahtarı gerekir)",
    "kind": "deepl",
    "base_url": "",
    "model": "",
    "timeout": None,
}

_FAKE_PROFILE = {
    "name": "Test (İşaretleme: [dil] kaynak metin)",
    "kind": "fake",
    "base_url": "",
    "model": "fake",
    "timeout": None,
}

_DEFAULT_PROFILES = [
    {
        "name": "LM Studio (1234)",
        "kind": "openai",
        "base_url": "http://localhost:1234/v1",
        "model": "",
        "timeout": None,
    },
    {
        "name": "Ollama (11434)",
        "kind": "openai",
        "base_url": "http://localhost:11434/v1",
        "model": "",
        "timeout": None,
    },
    _DEEPL_PROFILE,
    _FAKE_PROFILE,
]

#: Kinds that must appear in the list even for someone whose saved profiles predate them.
#: Without this a user who has ever opened the settings dialog would never see DeepL offered.
_ALWAYS_PRESENT = (_DEEPL_PROFILE, _FAKE_PROFILE)


@dataclass
class ProviderProfile:
    # Kayıtlı sağlayıcı profil veri modeli / Saved provider profile data model
    name: str
    kind: str = "openai"
    base_url: str = "http://localhost:1234/v1"
    model: str = ""
    timeout: float | None = None
    #: Optional heading this endpoint is filed under, e.g. "Yerel" or "Bulut". Empty means
    #: ungrouped, which is how every profile saved before grouping existed reads back.
    group: str = ""

    def to_config(self) -> ProviderConfig:
        if self.kind == "fake":
            return ProviderConfig(kind="fake", model="fake")
        from layoutkeep.ui import keyring_store
        from layoutkeep.ui.api_key_helpers import keyring_id

        return ProviderConfig(
            kind=self.kind,
            base_url=self.base_url,
            model=self.model,
            api_key=keyring_store.get_api_key(keyring_id(self.kind, self.base_url)),
            timeout=self.timeout,
        )


class ProviderProfileStore:
    # Profilleri kalıcı olarak saklayan ve yöneten sınıf / Store managing provider profiles

    def __init__(self) -> None:
        self._settings = app_settings()

    def list_profiles(self) -> list[ProviderProfile]:
        # Kayıtlı tüm profilleri listeler / Lists all stored provider profiles
        raw = self._settings.value(_SETTINGS_KEY_PROFILES, None)
        if not raw:
            return [ProviderProfile(**item) for item in _DEFAULT_PROFILES]
        try:
            items = json.loads(str(raw))
            profiles = [ProviderProfile(**item) for item in items]
            for spec in _ALWAYS_PRESENT:
                if not any(p.kind == spec["kind"] for p in profiles):
                    profiles.append(ProviderProfile(**spec))
            return profiles
        except (ValueError, TypeError):
            return [ProviderProfile(**item) for item in _DEFAULT_PROFILES]

    def save_profiles(self, profiles: list[ProviderProfile]) -> None:
        # Profil listesini kalıcı olarak kaydeder / Saves profile list to settings
        data = [asdict(p) for p in profiles]
        self._settings.setValue(_SETTINGS_KEY_PROFILES, json.dumps(data))

    def get_active_profile_name(self) -> str:
        # Son kullanılan aktif profil adını döndürür / Returns last used active profile name
        profiles = self.list_profiles()
        fallback = profiles[0].name if profiles else "LM Studio (1234)"
        return str(self._settings.value(_SETTINGS_KEY_ACTIVE, fallback))

    def set_active_profile_name(self, name: str) -> None:
        # Aktif profil adını kaydeder / Sets and saves active profile name
        self._settings.setValue(_SETTINGS_KEY_ACTIVE, name)

    def get_profile(self, name: str) -> ProviderProfile | None:
        # İsme göre profili getirir / Finds profile by name
        for p in self.list_profiles():
            if p.name == name:
                return p
        return None

    def move_profile(self, name: str, offset: int) -> None:
        """Move one endpoint up or down the list.

        The stored order is the order the interface shows, so this is all "reordering" needs
        to be. Moving past either end does nothing rather than wrapping around - a list that
        jumps from top to bottom under a repeated click is hard to aim.
        """
        profiles = self.list_profiles()
        names = [p.name for p in profiles]
        if name not in names:
            return
        index = names.index(name)
        target = index + offset
        if not 0 <= target < len(profiles):
            return
        profiles.insert(target, profiles.pop(index))
        self.save_profiles(profiles)

    def groups(self) -> list[str]:
        """Group names in the order they first appear, ungrouped entries excluded."""
        seen: list[str] = []
        for profile in self.list_profiles():
            if profile.group and profile.group not in seen:
                seen.append(profile.group)
        return seen

    def upsert_profile(self, profile: ProviderProfile) -> None:
        # Profili ekler veya günceller / Inserts or updates a profile
        profiles = self.list_profiles()
        found = False
        for idx, p in enumerate(profiles):
            if p.name == profile.name:
                profiles[idx] = profile
                found = True
                break
        if not found:
            profiles.append(profile)
        self.save_profiles(profiles)
        self.set_active_profile_name(profile.name)

    def delete_profile(self, name: str) -> None:
        # Profili listeden siler / Removes a profile from list
        profiles = [p for p in self.list_profiles() if p.name != name]
        if not profiles:
            profiles = [ProviderProfile(**item) for item in _DEFAULT_PROFILES]
        self.save_profiles(profiles)
        self.set_active_profile_name(profiles[0].name)
