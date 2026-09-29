"""Every setting the dialog offers is a setting the code reads.

The bug this guards against, reported as "find the settings that are not wired into the
application": `timeout.first_batch_s` sat in the Basic section of the settings dialog, could be
edited and saved, and was read by nothing - the timeout came from a constant. A switch that does
nothing is worse than no switch: it costs the reader trust in the ones that do work.

The check is deliberately simple and slightly over-eager: a key has to appear as a string literal
somewhere outside `tunables.py`. That is enough to catch a declaration nobody wired up, and it
cannot produce a false failure for a key that is read through a module-level constant (the style
this project uses, e.g. `_MIN_SCALE_KEY = "fit.min_scale"`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from layoutkeep.core import tunables

ROOT = Path(__file__).resolve().parents[1]


def _source_blob() -> str:
    parts = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path.name == "tunables.py":
            continue
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_no_declared_setting_is_unread() -> None:
    blob = _source_blob()
    unread = [spec.key for spec in tunables.TUNABLES if f'"{spec.key}"' not in blob]
    assert not unread, (
        "these settings are offered in the dialog but nothing reads them: " + ", ".join(unread)
    )


def test_the_first_batch_timeout_setting_reaches_the_timeout() -> None:
    """The specific switch that was dead: raising it must raise the first batch's timeout."""
    sys.path.insert(0, str(ROOT / "src"))
    from layoutkeep.ui.worker import _batch_timeout

    before = tunables.get("timeout.first_batch_s")
    try:
        tunables.set_value("timeout.first_batch_s", 600.0)
        assert _batch_timeout(1000, is_first=True, chars_per_second=None) >= 600.0
        tunables.set_value("timeout.first_batch_s", 40.0)
        assert _batch_timeout(0, is_first=True, chars_per_second=None) == pytest.approx(40.0)
    finally:
        tunables.set_value("timeout.first_batch_s", before)


def test_the_warm_batches_do_not_use_the_first_batch_allowance() -> None:
    """The setting is about the cold start only; warm batches keep their own, smaller base."""
    sys.path.insert(0, str(ROOT / "src"))
    from layoutkeep.ui.worker import _batch_timeout

    before = tunables.get("timeout.first_batch_s")
    try:
        tunables.set_value("timeout.first_batch_s", 900.0)
        assert _batch_timeout(0, is_first=False, chars_per_second=1000.0) < 100.0
    finally:
        tunables.set_value("timeout.first_batch_s", before)


def test_the_parallel_default_is_conservative() -> None:
    """Two, not seven: one local GPU sharing its context across seven requests was the wrong
    default for a first run (the user can raise it once the server has the slots)."""
    assert int(tunables.definition("translation.workers").default) == 2


def test_the_settings_dialog_shows_every_declared_setting() -> None:
    """Nothing is declared in the tunables and then left off the dialog either."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    app = QApplication.instance() or QApplication([])
    dialog = TweaksDialog()
    shown = set(dialog._editors)
    declared = {spec.key for spec in tunables.TUNABLES}
    assert declared - shown == set(), f"missing from the dialog: {sorted(declared - shown)}"
    assert shown - declared == set(), f"on the dialog but not declared: {sorted(shown - declared)}"
    dialog.deleteLater()
    app.processEvents()
