"""Single home for the crash-report path, shared by the GUI entry point and the worker thread.

Both `app.py` (uncaught GUI exceptions) and `worker.py` (worker-thread crashes) used to each
inline their own copy of this path. That duplication was a drift risk: one side changed to
`QStandardPaths.AppDataLocation` and the other could lag behind, re-introducing the bug where a
packaged app launched from Program Files cannot write the log (write fails, OSError swallowed,
the dialog still tells the user to read a file that was never created). One function, both call
sites, and a regression test pin it.
"""

from __future__ import annotations

from pathlib import Path


def crash_log_path() -> Path:
    """Where a crash report can actually be written.

    Uses the application data directory rather than the current working directory, which for a
    packaged app is wherever it happened to be launched from. In portable mode that directory
    sits beside the executable, so a crash on someone else's machine leaves its report on the
    stick with the program instead of in their profile.
    """
    from layoutkeep.core.paths import data_dir

    return data_dir() / "layoutkeep_crash.log"
