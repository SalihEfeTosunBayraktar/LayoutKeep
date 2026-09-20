r"""Shared test setup.

The UI persists preferences through QSettings, which on Windows is the real registry under
`HKCU\Software\LayoutKeep`. Without isolation the test suite reads and writes the
developer's own application settings: running the tests changed the saved output format,
provider profiles, theme and interface language.

It also made the suite non-deterministic. `test_ui_format_selector` selects `.docx`, which
`_on_format_changed` persists; a later `JobSetupWidget` then restores `.docx` and
`test_browsing_input_prefills_output_path` - which expects the source extension - fails.
Whether it failed depended on what happened to be stored on the machine at the time.

This file used to call `QSettings.setDefaultFormat` and `setPath`, which does nothing for the
two-argument `QSettings(org, app)` constructor the application uses: the isolation silently
had no effect for as long as it existed, and a test run corrupted a provider profile a user
was actively translating with. Settings now go through `ui.settings.app_settings`, which puts
them in a file when the data directory is chosen explicitly - so pointing LAYOUTKEEP_DATA_DIR
at a temporary directory is what actually isolates them.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6")

#: Tests must never open the modal welcome screen: there is nobody to dismiss it, and the session
#: waits in `exec()` forever.
ENV_NO_WELCOME = "LAYOUTKEEP_NO_WELCOME"



@pytest.fixture(autouse=True, scope="session")
def _no_first_run_dialog() -> Iterator[None]:
    """The introduction is modal, and a test session has nobody to click it away.

    Found the hard way: the suite sat at 89% for fifteen minutes with a PySide6 event loop
    waiting for input, because a test constructed the main window and the first-run timer fired.
    """
    previous = os.environ.get(ENV_NO_WELCOME)
    os.environ[ENV_NO_WELCOME] = "1"
    yield
    if previous is None:
        os.environ.pop(ENV_NO_WELCOME, None)
    else:
        os.environ[ENV_NO_WELCOME] = previous


@pytest.fixture(autouse=True)
def _language_back_to_english():
    """The interface language is global state; no test may leak it into the next one.

    WHY THIS EXISTS: a test that pinned German left it set, and the next file's pause-button
    assertion ("Duraklat") failed with "Pause" - a leak that reads as a broken widget rather than
    as a stray global.
    """
    yield
    from layoutkeep.ui.strings import UIStrings

    UIStrings.set_language("en")


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """Answer every message box instead of showing one.

    `QMessageBox.warning` blocks until someone clicks it, and on a headless runner nobody ever
    does: the suite stopped dead for twenty-five minutes on one test with no output and no
    failure, which reads as a hung machine rather than a test asking a question. It was asking a
    question - a validation error had opened a dialog.

    The calls are recorded on the class so a test can assert that the user was warned, which is
    usually the thing worth asserting anyway.
    """
    from PySide6.QtWidgets import QMessageBox

    shown: list[tuple[str, str, str]] = []

    def record(kind, default):
        def call(_parent=None, title="", text="", *args, **kwargs):
            shown.append((kind, str(title), str(text)))
            return default
        return call

    monkeypatch.setattr(QMessageBox, "warning", record("warning", QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "critical", record("critical", QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(
        QMessageBox, "information", record("information", QMessageBox.StandardButton.Ok)
    )
    monkeypatch.setattr(QMessageBox, "question", record("question", QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "exec_", lambda self: QMessageBox.StandardButton.Ok, raising=False)
    QMessageBox.shown_in_test = shown
    yield shown
    QMessageBox.shown_in_test = []


def pytest_collection_modifyitems(config, items):
    """Skip the tests that need a real OCR engine when one is not installed.

    `rapidocr` and its ONNX runtime are the heaviest thing this project depends on and CI does
    not install them - reasonably, since image conversion is locked (see
    docs/ENGINE-ARCHITECTURE.md). Their absence used to stop pytest collecting eight modules
    outright, which reads as "the build is broken" rather than "this optional engine is not
    here". Pillow and numpy, which the fixtures need to draw their own images, are ordinary test
    dependencies and are declared as such in pyproject.toml.
    """
    try:
        import rapidocr  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(reason="OCR engine (rapidocr) not installed")
        for item in items:
            if any(name in str(item.fspath) for name in _OCR_TEST_MODULES):
                item.add_marker(skip)


#: Test modules that cannot run a step without the OCR engine actually being present.
_OCR_TEST_MODULES = (
    "test_ocr_engine",
    "test_inpaint",
    "test_image_reader",
    "test_image_writer",
    "test_conversion_matrix",
    "test_cross_format",
    "test_outlined_text",
)

from layoutkeep.core import paths
from layoutkeep.ui import settings


@pytest.fixture(scope="session", autouse=True)
def _isolate_qsettings(tmp_path_factory: pytest.TempPathFactory):
    # Ayarları geçici dizine yönlendirir / Redirects settings to a temporary directory
    settings_dir = tmp_path_factory.mktemp("qsettings")
    import os

    previous = os.environ.get(paths.ENV_DATA_DIR)
    os.environ[paths.ENV_DATA_DIR] = str(settings_dir)

    # The guard the old fixture lacked: if this ever stops working, the suite says so here
    # rather than by quietly editing the machine it runs on.
    written = settings.settings_path()
    assert written is not None and str(settings_dir) in written, (
        f"settings are not isolated - they would be written to {written}"
    )

    yield settings_dir

    if previous is None:
        os.environ.pop(paths.ENV_DATA_DIR, None)
    else:
        os.environ[paths.ENV_DATA_DIR] = previous


@pytest.fixture(scope="session")
def _figures_report_as_read():
    """The 23-figure NASA report, read once for the whole run.

    Eleven conversion tests read this same PDF, each for about 90 seconds - more than half of a
    19.5-minute suite. The reading is the same every time; what the tests check is the writers.
    """
    from pathlib import Path

    from layoutkeep.writers.converter import read_any_document

    src = Path("_artifacts/corpus/nasa_report.pdf")
    if not src.exists():
        pytest.skip("corpus PDF not available")
    return src, read_any_document(src)


@pytest.fixture
def figures_report(_figures_report_as_read):
    """(source path, a private copy of its document): tests translate and write it."""
    import copy

    src, doc = _figures_report_as_read
    return src, copy.deepcopy(doc)


@pytest.fixture(scope="session", autouse=True)
def _no_installed_layout_model(tmp_path_factory: pytest.TempPathFactory):
    """Tests read without the layout model a developer's machine may have installed.

    The CLI and the desktop worker use it whenever it is installed, so without this a test's
    reading - and its result - would depend on what happens to be in LOCALAPPDATA. Tests that
    exercise the model pass a detector of their own.
    """
    import os

    from layoutkeep.ocr.layout_detector import ENV_MODEL


    previous = os.environ.get(ENV_MODEL)
    os.environ[ENV_MODEL] = str(tmp_path_factory.mktemp("no_layout_model") / "absent.onnx")
    yield
    if previous is None:
        os.environ.pop(ENV_MODEL, None)
    else:
        os.environ[ENV_MODEL] = previous
