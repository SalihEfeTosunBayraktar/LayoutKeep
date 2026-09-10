"""Where the application's settings are written.

This module exists because the answer was wrong for two features at once and nobody noticed:
`QSettings.setDefaultFormat` does not affect the `QSettings(organization, application)`
constructor, so portable mode wrote its settings into the host machine's registry and the test
suite rewrote the developer's own provider profiles - once destroying a profile a user was
translating with at the time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.core import paths
from layoutkeep.ui import settings


def test_an_installed_copy_uses_the_per_user_system_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)

    assert settings.settings_path() is None


def test_a_portable_copy_keeps_its_settings_beside_the_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Most of what "portable" has to mean: the stick carries the configuration and the host
    machine keeps none of it."""
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)
    (tmp_path / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)

    path = settings.settings_path()

    assert path is not None
    assert Path(path).parent == tmp_path / paths.PORTABLE_DIR_NAME


def test_the_data_directory_override_moves_the_settings_with_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The lever the test suite pulls; if it stops working the suite edits a real machine."""
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path))

    path = settings.settings_path()

    assert path is not None and Path(path).parent == tmp_path


def test_settings_written_here_are_read_back_from_that_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A path is not proof; write through the real object and find the file on disk."""
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path))

    store = settings.app_settings()
    store.setValue("target_lang", "de")
    store.sync()

    written = Path(settings.settings_path())
    assert written.exists()
    assert "de" in written.read_text(encoding="utf-8")
    assert settings.app_settings().value("target_lang") == "de"
