"""API key storage in the OS keychain, never in a plain file (see docs/CONTRACT.md §6).

Thin wrapper so the rest of the UI never imports `keyring` directly.
"""

from __future__ import annotations

import contextlib

import keyring

_SERVICE = "layoutkeep"


def set_api_key(base_url: str, api_key: str) -> None:
    keyring.set_password(_SERVICE, base_url, api_key)


def get_api_key(base_url: str) -> str | None:
    return keyring.get_password(_SERVICE, base_url)


def delete_api_key(base_url: str) -> None:
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(_SERVICE, base_url)
