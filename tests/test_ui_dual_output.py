"""The bilingual PDF is reachable from the application, not only from the command line.

Twice now a capability existed in the CLI and nowhere in the UI (the glossary and memory, then
parallelism), and both times the user experienced it as "the feature does not exist". This file
holds the same line for the bilingual output: the setup screen carries the choice, the job carries
it, and the worker writes the second file - asserted through the real objects, not by reading the
source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_pdf_fixture


def _pdf_job(tmp_path: Path, **overrides) -> JobConfig:
    source = tmp_path / "sample.pdf"
    build_pdf_fixture.build_single_column(source)
    defaults = {
        "input_path": str(source),
        "output_path": str(tmp_path / "sample.out.pdf"),
        "source_lang": "en",
        "target_lang": "tr",
        "provider": ProviderConfig(kind="fake"),
    }
    defaults.update(overrides)
    return JobConfig(**defaults)


def test_the_bilingual_choice_lives_in_the_settings(qtbot) -> None:
    """Moved off the setup screen on request: a rarely used output extra, edited in the settings.

    The old test pinned the combo in the setup screen. It now pins both halves of the move - the
    screen no longer carries it, and the settings offer the same three values with "off" as default.
    """
    from layoutkeep.ui.job_setup import JobSetupWidget
    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    screen = JobSetupWidget()
    qtbot.addWidget(screen)
    assert not hasattr(screen, "_dual_mode"), "the setup screen must not carry the choice any more"

    dialog = TweaksDialog()
    qtbot.addWidget(dialog)
    editor = dialog._editors["output.dual_mode"]
    values = [editor.itemData(row) for row in range(editor.count())]
    assert values == ["", "side", "alternate"], values
    assert editor.currentData() == "", "the default must be off"


def test_the_settings_choice_reaches_the_job(qtbot, tmp_path) -> None:
    """Through the real screen: the choice is a tunable now, and the job must still receive it.

    The first version pointed the screen at a Python file and returned early when it was refused,
    which passed whether or not the wiring existed - a test that cannot fail is not a test. This
    one builds a real PDF, so the emit is expected to happen.
    """
    from layoutkeep.core import tunables
    from layoutkeep.ui.job_setup import JobSetupWidget

    source = tmp_path / "sample.pdf"
    build_pdf_fixture.build_single_column(source)
    tunables.set_value("output.dual_mode", "alternate")
    try:
        screen = JobSetupWidget()
        qtbot.addWidget(screen)
        captured: list[JobConfig] = []
        screen.job_ready.connect(captured.append)
        screen._input_path.setText(str(source))

        screen._emit_job()

        assert captured, "the screen refused a valid PDF"
        assert captured[0].dual_mode == "alternate"
    finally:
        tunables.reset_all()


def test_the_worker_writes_the_bilingual_file(tmp_path) -> None:
    config = _pdf_job(tmp_path, dual_mode="side")

    TranslationWorker(config).run()

    dual = Path(config.output_path).with_name("sample.out.dual.pdf")
    assert dual.exists(), "the bilingual file was not written"
    with pymupdf.open(str(dual)) as composed, pymupdf.open(config.output_path) as single:
        assert composed.page_count == single.page_count
        assert composed[0].rect.width > single[0].rect.width, "side by side must be wider"


def test_no_dual_file_without_the_choice(tmp_path) -> None:
    config = _pdf_job(tmp_path)

    TranslationWorker(config).run()

    assert not Path(config.output_path).with_name("sample.out.dual.pdf").exists()


def test_an_alternating_bilingual_file_has_twice_the_pages(tmp_path) -> None:
    config = _pdf_job(tmp_path, dual_mode="alternate")

    TranslationWorker(config).run()

    dual = Path(config.output_path).with_name("sample.out.dual.pdf")
    with pymupdf.open(str(dual)) as composed, pymupdf.open(config.output_path) as single:
        assert composed.page_count == single.page_count * 2
