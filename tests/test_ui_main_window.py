"""Tests for MainWindow, HeaderBar, and theme switching."""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.ui.main_window import MainWindow
from layoutkeep.ui.theme import ThemeManager


def test_main_window_initialization(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "LayoutKeep"
    assert window._header is not None
    assert window._stack.count() == 3
    assert window._stack.currentWidget() == window._setup


def test_header_theme_toggle_updates_theme(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    initial_dark = ThemeManager.is_dark()
    window._header._theme_btn.click()
    assert ThemeManager.is_dark() == (not initial_dark)

    window._header._theme_btn.click()
    assert ThemeManager.is_dark() == initial_dark


def test_the_finished_step_offers_a_way_out(qtbot, tmp_path, monkeypatch):
    """Step 3 must not be a dead end.

    The translation finishes and the completion screen must offer: open the produced file,
    show it in a folder, and go back to start another job - with the output path shown.
    """
    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")

    from layoutkeep.ui.job import JobConfig, ProviderConfig
    from layoutkeep.ui.worker import TranslationWorker

    src = Path("_artifacts/input/single_column.pdf")
    if not src.exists():
        pytest.skip("fixture PDF not available")

    out = tmp_path / "cikti.pdf"
    project = tmp_path / "p.lkproj"
    window = MainWindow()
    qtbot.addWidget(window)

    config = JobConfig(
        input_path=str(src),
        output_path=str(out),
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake"),
        project_path=str(project),
    )
    window._last_output_path = config.output_path
    TranslationWorker(config).run()
    window._on_finished(str(project))

    completion = window._completion
    assert window._stack.currentIndex() + 1 == 3
    assert out.name in completion._output_label.text(), "the produced file is not named anywhere"
    assert completion._open_btn.isEnabled()
    assert completion._folder_btn.isEnabled()

    completion.back_to_setup_requested.emit()
    assert window._stack.currentIndex() + 1 == 1, "no way back to the setup step"


def test_nothing_is_offered_to_open_when_the_output_is_missing(qtbot, tmp_path):
    """Enabled buttons that fail on click are worse than disabled ones."""
    from layoutkeep.ui.completion import CompletionWidget

    completion = CompletionWidget()
    qtbot.addWidget(completion)

    completion.set_output_path(str(tmp_path / "never_written.pdf"))

    assert not completion._open_btn.isEnabled()
    assert not completion._folder_btn.isEnabled()
    assert completion._output_label.text() == ""
