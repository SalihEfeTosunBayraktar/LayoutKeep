"""Where LayoutKeep keeps its data, and how portable mode changes that.

Normally settings, tunables and crash reports go to the per-user application data directory,
which is right for an installed application: they follow the user between versions and survive
uninstalling the program.

That is exactly wrong for a copy carried on a USB stick. A portable build should leave nothing
behind on the host machine and should keep its configuration with the executable, so plugging
the stick into another computer carries the settings along.

Portable mode is opt-in and explicit: a file named `portable.txt` beside the executable turns
it on. Detecting it automatically from "am I a single file?" would be a guess, and a wrong
guess here either scatters files across someone's machine or hides their settings from them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Presence of this file next to the executable switches on portable mode.
PORTABLE_MARKER = "portable.txt"

#: Where a portable installation keeps everything, relative to the executable.
PORTABLE_DIR_NAME = "LayoutKeepData"

#: Overrides everything, for tests and for anyone who wants the data somewhere specific.
ENV_DATA_DIR = "LAYOUTKEEP_DATA_DIR"


def executable_dir() -> Path:
    """The directory the running program sits in.

    Under PyInstaller `sys.executable` is the bundled exe, which is what "beside the
    executable" has to mean - `sys._MEIPASS` is a temporary unpack directory that is deleted
    on exit, so writing settings there would silently discard them.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd()


def is_portable() -> bool:
    return (executable_dir() / PORTABLE_MARKER).exists()


def data_dir_is_explicit() -> bool:
    """Whether the data directory was chosen rather than defaulted.

    True for a portable copy and for the environment override; False when settings belong in
    the per-user system location, which on Windows is the registry.
    """
    return bool(os.environ.get(ENV_DATA_DIR)) or is_portable()


def data_dir() -> Path:
    """The directory for settings, tunables and crash reports."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override)
    if is_portable():
        return executable_dir() / PORTABLE_DIR_NAME
    base = os.environ.get("APPDATA") or Path.home()
    return Path(base) / "LayoutKeep"


def ensure_data_dir() -> Path:
    """The data directory, created if need be.

    A portable copy can sit on read-only media or in a directory the user cannot write to. In
    that case fall back to the per-user location rather than failing to start - losing portable
    behaviour is a far smaller problem than an application that will not open.
    """
    target = data_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        base = os.environ.get("APPDATA") or Path.home()
        target = Path(base) / "LayoutKeep"
        target.mkdir(parents=True, exist_ok=True)
    return target
