"""The heavy C extensions must load on the main thread, not inside a job's worker.

On 2026-09-22 the packaged build died twice at the same place: numpy (and behind it OpenCV and
onnxruntime) was imported lazily, on the worker thread, the first time a job read a document - once
as "Fatal Python error: Aborted" during a garbage collection on the main thread, once as an access
violation beside the progress timer's tick. `app.main` now warms those modules before the event
loop starts, and these tests keep that honest.
"""

from __future__ import annotations

import sys

from layoutkeep.ui.app import _HEAVY_MODULES, _warm_heavy_imports


def test_every_heavy_module_imports_cleanly():
    assert _warm_heavy_imports() == []


def test_the_warmup_covers_the_readers_and_the_layout_detector():
    names = set(_HEAVY_MODULES)
    assert "layoutkeep.readers.pdf_reader" in names
    assert "layoutkeep.readers.image_reader" in names
    assert "layoutkeep.ocr.layout_detector" in names


def test_a_module_that_fails_does_not_stop_the_warmup(monkeypatch):
    """An absent optional reader must not keep the app from starting."""
    import layoutkeep.ui.app as app

    monkeypatch.setattr(app, "_HEAVY_MODULES", ("layoutkeep.readers.does_not_exist", "sys"))
    assert app._warm_heavy_imports() == ["layoutkeep.readers.does_not_exist"]
    assert "sys" in sys.modules
