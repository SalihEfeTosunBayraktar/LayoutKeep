"""The one place a QSettings object is constructed.

There was no such place, and three call sites wrote `QSettings("LayoutKeep", "LayoutKeep")`
directly. On Windows that is the registry, and two features tried to move it the same wrong
way: portable mode and the test suite both called `QSettings.setDefaultFormat` plus
`setPath`. Neither works - the two-argument constructor ignores the default format - so
portable copies wrote their settings into the host machine's registry, and running the tests
rewrote the developer's own provider profiles. That is how a test run came to delete a real
DeepL profile's kind while the application was using it.

Naming the format explicitly is what actually decides the location, so this function does
that, and everything else asks it rather than constructing its own.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from layoutkeep.core import paths

ORGANIZATION = "LayoutKeep"
APPLICATION = "LayoutKeep"

#: File name used when the settings live in a directory of our choosing.
SETTINGS_FILE = "LayoutKeep.ini"


def settings_path() -> str | None:
    """The file settings belong in, or None for the per-user system location.

    A portable copy keeps them beside the executable, and `LAYOUTKEEP_DATA_DIR` overrides
    everything - which is what lets a test run leave the real settings untouched.
    """
    if paths.data_dir_is_explicit():
        return str(paths.data_dir() / SETTINGS_FILE)
    return None


def app_settings() -> QSettings:
    """Settings for this application, in whichever location is in force."""
    path = settings_path()
    if path is not None:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings(ORGANIZATION, APPLICATION)
