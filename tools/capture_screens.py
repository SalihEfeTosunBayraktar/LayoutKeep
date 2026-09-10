"""Render every application screen to docs/screenshots/.

Runs the real widgets - the same classes the application shows - rather than mock-ups, so a
screen that has drifted from its design is visible here. Offscreen by default, so it works on
a machine with no display and in CI.

    .venv/Scripts/python.exe tools/capture_screens.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# The native platform on purpose. Under "offscreen" Qt finds no system fonts on Windows and
# every glyph renders as a tofu box, which makes the captures worthless as design references.
# Set QT_QPA_PLATFORM=offscreen explicitly if you are on a headless machine and accept that.
os.environ.setdefault("LAYOUTKEEP_TUNABLES", str(Path(tempfile.mkdtemp()) / "tunables.json"))

from PySide6.QtWidgets import QApplication

from layoutkeep.core import paths

OUT_DIR = ROOT / "docs" / "screenshots"

#: Do not resize. MainWindow opens at 880x620 (main_window.py), and forcing a wider window
#: for the captures produced pictures that did not match what the application actually shows -
#: the same layout with 45% more room to breathe in. A screenshot that flatters the app is
#: worse than none, because it hides exactly the crowding a user reports.


def _isolate_settings() -> None:
    """Keep a capture run from rewriting the developer's own saved preferences.

    This used to set the QSettings default format, which the application's constructor
    ignores - so the captures were quietly editing the real settings. The data-directory
    override is what actually moves them (see ui/settings.py).
    """
    os.environ[paths.ENV_DATA_DIR] = str(Path(tempfile.mkdtemp()))
    from layoutkeep.ui import settings

    assert settings.settings_path() is not None, "capture run is not isolated"


def _save(widget, name: str) -> Path:
    widget.show()
    QApplication.processEvents()
    target = OUT_DIR / f"{name}.png"
    widget.grab().save(str(target))
    widget.hide()
    return target


def _sample_job(tmp: Path):
    from layoutkeep.ui.job import JobConfig, ProviderConfig

    return JobConfig(
        input_path=str(ROOT / "_artifacts/input/two_column.pdf"),
        output_path=str(tmp / "AI_Research_Paper.out.pdf"),
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake", model="fake"),
        project_path=str(tmp / "job.lkproj"),
    )


def capture(theme_dark: bool) -> list[Path]:
    from layoutkeep.ui.main_window import MainWindow
    from layoutkeep.ui.theme import ThemeManager
    from layoutkeep.ui.tweaks_dialog import TweaksDialog
    from layoutkeep.ui.worker import TranslationWorker

    suffix = "dark" if theme_dark else "light"
    tmp = Path(tempfile.mkdtemp())
    written: list[Path] = []
    window = MainWindow()

    # After the window, not before. MainWindow.__init__ restores the theme from settings and
    # calls ThemeManager.set_dark itself, so setting it first was silently overridden - half
    # the captures came out in the wrong theme while carrying the right file name.
    ThemeManager.set_dark(theme_dark)
    window._on_theme_changed(theme_dark)
    window._header.apply_theme() if hasattr(window._header, "apply_theme") else None
    QApplication.processEvents()
    assert ThemeManager.is_dark() is theme_dark

    # 1. setup
    written.append(_save(window, f"01_setup_{suffix}"))

    # 2. progress, with a job actually run so the panes and counters hold real content
    config = _sample_job(tmp)
    window._last_output_path = config.output_path
    window._stack.setCurrentWidget(window._progress)
    window._header.set_active_step(2)
    window._progress.start(total_segments=3, total_chars=400)

    worker = TranslationWorker(config)
    worker.segment_translated.connect(window._progress.append_segment_pair)
    worker.review_flags.connect(window._progress.set_review_flags)
    worker.job_stats.connect(window._completion.set_stats)
    worker.progress.connect(window._progress.set_progress)
    worker.run()
    written.append(_save(window, f"02_progress_{suffix}"))

    # 3. completion, holding that job's real figures
    window._on_finished(str(tmp / "job.lkproj"))
    written.append(_save(window, f"03_completion_{suffix}"))

    # 4/5. the settings dialog, both tabs
    dialog = TweaksDialog(window)
    dialog.resize(760, 720)
    dialog.show()
    QApplication.processEvents()
    from PySide6.QtWidgets import QTabWidget

    tab_widget = dialog.findChild(QTabWidget)
    for index, label in enumerate(("04_settings_basic", "05_settings_advanced")):
        tab_widget.setCurrentIndex(index)
        QApplication.processEvents()
        target = OUT_DIR / f"{label}_{suffix}.png"
        dialog.grab().save(str(target))
        written.append(target)
    dialog.hide()

    # 6. provider settings
    from layoutkeep.ui.provider_settings import ProviderSettingsDialog

    provider_dialog = ProviderSettingsDialog(parent=window)
    provider_dialog.resize(700, 520)
    provider_dialog.show()
    QApplication.processEvents()
    target = OUT_DIR / f"06_provider_settings_{suffix}.png"
    provider_dialog.grab().save(str(target))
    written.append(target)
    provider_dialog.hide()

    window.close()
    return written


def main() -> int:
    _isolate_settings()
    QApplication.instance() or QApplication([])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for dark in (True, False):
        written.extend(capture(dark))

    print(f"{len(written)} ekran goruntusu yazildi -> {OUT_DIR}")
    for path in written:
        print(f"  {path.name:<36} {path.stat().st_size // 1024:>5} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
