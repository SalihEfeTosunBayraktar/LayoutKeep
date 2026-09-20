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


def test_the_setup_screen_offers_the_bilingual_choice(qtbot) -> None:
    from layoutkeep.ui.job_setup import JobSetupWidget

    screen = JobSetupWidget()
    qtbot.addWidget(screen)
    values = [screen._dual_mode.itemData(row) for row in range(screen._dual_mode.count())]
    assert values == ["", "side", "alternate"], values
    assert screen._dual_mode.currentData() == "", "the default must be off"


def test_the_setup_screen_carries_the_choice_into_the_job(qtbot, tmp_path) -> None:
    """Through the real screen: pick a file, pick "alternate", emit, read the job.

    The first version pointed the screen at a Python file and returned early when it was refused,
    which passed whether or not the wiring existed - a test that cannot fail is not a test. This
    one builds a real PDF, so the emit is expected to happen.
    """
    from layoutkeep.ui.job_setup import JobSetupWidget

    source = tmp_path / "sample.pdf"
    build_pdf_fixture.build_single_column(source)
    screen = JobSetupWidget()
    qtbot.addWidget(screen)
    captured: list[JobConfig] = []
    screen.job_ready.connect(captured.append)
    screen._input_path.setText(str(source))
    screen._dual_mode.setCurrentIndex(screen._dual_mode.findData("alternate"))

    screen._emit_job()

    assert captured, "the screen refused a valid PDF"
    assert captured[0].dual_mode == "alternate"


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
