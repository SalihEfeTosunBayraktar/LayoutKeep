"""Helpers for persisting API keys in the OS keyring.

OS anahtar halkasında API anahtarı saklamak için tek sorumluluklu yardımcılar.
"""

from __future__ import annotations

from layoutkeep.ui import keyring_store


def save_api_key_for(base_url: str, raw_key: str) -> None:
    """Persist the provided key for the base URL, or delete the existing entry when empty.

    Base URL için API anahtarını kaydeder; alan boşsa eski kaydı siler.
    """
    if raw_key:
        keyring_store.set_api_key(base_url, raw_key)
    else:
        keyring_store.delete_api_key(base_url)


def load_api_key_for(base_url: str) -> str:
    """Return the stored key for the base URL, or an empty string if absent.

    Base URL için saklı anahtarı döndürür; yoksa boş string verir.
    """
    return keyring_store.get_api_key(base_url) or ""


def keyring_id(kind: str, base_url: str) -> str:
    """The identity a provider's key is stored under.

    An OpenAI-compatible server is identified by its base URL, which is what tells one apart
    from another. DeepL has no base URL to enter - the key itself decides whether the request
    goes to the free or the paid host - so keying on the URL would file every DeepL key under
    the empty string, and a second profile would silently overwrite the first.
    """
    return base_url.strip() or kind
