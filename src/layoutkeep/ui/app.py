"""GUI entry point with global exception handlers to prevent silent crashes.

Sessiz çökmeleri önleyen genel hata yakalayıcılı arayüz giriş noktası.
"""

from __future__ import annotations

import faulthandler
import sys
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from layoutkeep.ui.crashlog import crash_log_path
from layoutkeep.ui.main_window import MainWindow
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

#: Modules that pull in a C extension and are otherwise first imported by a job's worker thread -
#: the readers for every supported format, the writers, and the ONNX layout detector behind the
#: scanned-page path. Importing them at startup keeps that work off the worker.
_HEAVY_MODULES = (
    "layoutkeep.readers.pdf_reader",
    "layoutkeep.readers.epub_reader",
    "layoutkeep.readers.docx_reader",
    "layoutkeep.readers.image_reader",
    "layoutkeep.writers.pdf_generator",
    "layoutkeep.writers.epub_writer",
    "layoutkeep.ocr.layout_detector",
)


def _warm_heavy_imports() -> list[str]:
    """Load the heavy stack on the main thread, before the event loop and any job.

    Returns the names that failed. A failure must not stop the app: a reader that cannot import
    only means the job needing it will say so, exactly as it did before.
    """
    import importlib

    failed: list[str] = []
    for name in _HEAVY_MODULES:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - an optional reader may genuinely be absent
            failed.append(name)
    return failed


def _crash_log_path() -> Path:
    return crash_log_path()


def _log_exception(exc_type, exc_value, exc_tb) -> Path | None:
    # Hata ayrıntılarını konsola ve dosyaya yazar / Logs exception details to console and file
    msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if sys.stderr is not None:
        sys.stderr.write("\n[LayoutKeep CRITICAL ERROR]\n" + msg + "\n")
        sys.stderr.flush()
    path = _crash_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n--- CRASH LOG ---\n" + msg + "\n")
    except OSError:
        return None
    return path


def _enable_native_crash_log() -> None:
    """Keep the file open for the process lifetime so a hard crash still leaves a stack.

    Python's own hooks cover Python exceptions. They cover nothing when the process dies
    inside Qt - an access violation leaves the user with a window that vanished and us with
    an empty directory, which is exactly the position a DeepL crash report left us in. The
    faulthandler writes the C-level and Python-level stacks of every thread at the moment of
    the fault, into a file rather than the missing console of a windowed build.
    """
    try:
        path = _crash_log_path().with_name("layoutkeep_fault.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8")
    except OSError:
        return
    handle.write(f"\n--- session started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    handle.flush()
    faulthandler.enable(file=handle, all_threads=True)


def _exception_hook(exc_type, exc_value, exc_tb) -> None:
    # Ana iş parçacığı istisnalarını yakalar / Catches main thread exceptions
    path = _log_exception(exc_type, exc_value, exc_tb)
    if QApplication.instance() is not None:
        short_msg = f"{exc_type.__name__}: {exc_value}"
        where = (
            UIStrings.LOG_SAVED_TO.format(path) if path
            else UIStrings.LOG_SAVE_FAILED
        )
        QMessageBox.critical(
            None, "Beklenmeyen Hata", f"{short_msg}\n\n{where}"
        )


def _thread_exception_hook(args: threading.ExceptHookArgs) -> None:
    # Yan iş parçacığı istisnalarını yakalar / Catches background thread exceptions
    _log_exception(args.exc_type, args.exc_value, args.exc_traceback)


def main() -> int:
    # Uygulama giriş noktası ve kanca kurulumu / Application entry point and hook setup
    sys.excepthook = _exception_hook
    threading.excepthook = _thread_exception_hook
    _enable_native_crash_log()

    app = QApplication(sys.argv)
    # Names the per-user directories Qt derives - the settings QSettings already writes under
    # ("LayoutKeep", "LayoutKeep") and the folder a crash report goes to. Without them the
    # location is derived from the executable name, which differs between a dev run and the
    # packaged app.
    app.setOrganizationName("LayoutKeep")
    app.setApplicationName("LayoutKeep")
    # Every window and dialog inherits this; without it Windows shows its blank placeholder.
    from layoutkeep.ui.branding import app_icon

    app.setWindowIcon(app_icon())

    # Portable mode: keep settings beside the executable so a copy on a stick carries its
    # configuration and leaves nothing on the host machine. Must happen before any QSettings
    # is constructed, which means before any window exists.
    from layoutkeep.core import paths, tunables

    if paths.is_portable():
        # Only creates the directory. Where the settings file goes is decided by
        # `ui.settings.app_settings`, because the QSettings default-format switch this used to
        # call has no effect on the constructor the application uses - portable copies were
        # writing into the host machine's registry regardless.
        paths.ensure_data_dir()

    tunables.load()
    app.setStyleSheet(ThemeManager.get_stylesheet())
    window = MainWindow()
    window.show()

    # The C-extension stack used to load lazily, on the worker thread, the first time a job read a
    # document: numpy, OpenCV, onnxruntime and MuPDF's text machinery all arrive that way. That
    # import then ran while the main thread was ticking the progress timer or collecting garbage,
    # and the packaged build died on it on 2026-09-22 - "Fatal Python error: Aborted" with numpy
    # being imported inside the reader, and an access violation beside the progress tick. Loading
    # them here, on the main thread, before the event loop starts takes the race away.
    _warm_heavy_imports()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
