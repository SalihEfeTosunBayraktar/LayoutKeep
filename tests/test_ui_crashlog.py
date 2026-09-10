"""Regression tests for the shared crash-report path.

Pin the bug the reviewer flagged: the worker thread used to inline a copy of the crash-log path
that could drift from `app.py`. Both now go through `crashlog.crash_log_path`.

It must never resolve relative to the working directory - for a packaged app that is wherever
it happened to be launched from, and in a read-only location the write fails, the OSError is
swallowed, and the dialog still tells the user to go read a file that was never created.

The location itself moved from Qt's `QStandardPaths` to `core.paths.data_dir`, so that a
portable copy keeps its crash reports beside the executable rather than in the profile of
whoever's machine it was plugged into. These tests follow the mechanism but pin the same
guarantees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.core import paths
from layoutkeep.ui import crashlog


def test_crash_log_is_not_relative_to_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "data"))

    path = crashlog.crash_log_path()

    assert path == tmp_path / "data" / "layoutkeep_crash.log"
    assert Path.cwd() not in path.parents


def test_an_installed_copy_writes_into_the_user_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))

    assert crashlog.crash_log_path() == tmp_path / "roaming" / "LayoutKeep" / "layoutkeep_crash.log"


def test_a_portable_copy_writes_beside_the_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A crash on someone else's machine should leave its report on the stick, not in their
    profile - that is most of what "portable" has to mean."""
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)
    (tmp_path / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "executable_dir", lambda: tmp_path)

    path = crashlog.crash_log_path()

    assert path.parent == tmp_path / paths.PORTABLE_DIR_NAME


def test_the_worker_and_the_gui_agree_on_one_path() -> None:
    """The drift this module exists to prevent: two call sites, one function."""
    import inspect

    from layoutkeep.ui import app, worker

    for module in (app, worker):
        source = inspect.getsource(module)
        assert "crash_log_path" in source, f"{module.__name__} does not use the shared path"
        assert "QStandardPaths" not in source, f"{module.__name__} computes its own path again"
