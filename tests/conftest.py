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

import pytest

pytest.importorskip("PySide6")


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
