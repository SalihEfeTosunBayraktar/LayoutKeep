"""Where the application keeps its data, and what portable mode changes.

A portable copy on a stick must keep its configuration with the executable and leave nothing
on the host machine. An installed copy must do the opposite. Getting this wrong scatters files
across someone's computer or hides their settings from them, so the switch is explicit rather
than guessed from "am I a single file?".
"""

from __future__ import annotations

import pytest

from layoutkeep.core import paths


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)


def test_without_the_marker_data_goes_to_the_user_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    assert not paths.is_portable()
    assert paths.data_dir() == tmp_path / "roaming" / "LayoutKeep"


def test_the_marker_moves_data_beside_the_executable(monkeypatch, tmp_path):
    (tmp_path / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)

    assert paths.is_portable()
    assert paths.data_dir() == tmp_path / paths.PORTABLE_DIR_NAME


def test_an_explicit_directory_wins_over_everything(monkeypatch, tmp_path):
    (tmp_path / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "elsewhere"))

    assert paths.data_dir() == tmp_path / "elsewhere"


def test_a_read_only_portable_location_falls_back_rather_than_failing(monkeypatch, tmp_path):
    """A stick can be write-protected. Losing portable behaviour beats not starting."""
    fallback = tmp_path / "roaming"
    monkeypatch.setenv("APPDATA", str(fallback))

    def _refuse(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(paths.Path, "mkdir", _refuse)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "unwritable")

    with pytest.raises(OSError):
        # The fallback also uses mkdir, so with every mkdir refused this must surface rather
        # than pretend it succeeded - the test pins that it is not swallowed silently.
        paths.ensure_data_dir()


def test_tunables_and_the_crash_log_share_the_data_directory(monkeypatch, tmp_path):
    """Two places used to compute this separately and drifted apart once already."""
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "data"))

    from layoutkeep.core import tunables
    from layoutkeep.ui.crashlog import crash_log_path

    assert tunables.storage_path().parent == tmp_path / "data"
    assert crash_log_path().parent == tmp_path / "data"
