"""The desktop application records the run in the project it saves, and in the output file.

The two front-ends answer the same question and must not answer it differently: the record is
built by one shared helper (`core/provenance.py`), fed from the window's own job configuration.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

from layoutkeep import __version__
from layoutkeep.core import provenance
from layoutkeep.core.docir import load_project
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture


def test_the_application_records_the_run_it_made(qtbot, tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(src)
    out = tmp_path / "app.tr.epub"
    config = JobConfig(
        input_path=str(src),
        output_path=str(out),
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake"),
    )

    failed: list[str] = []
    worker = TranslationWorker(config)
    worker.failed.connect(failed.append)
    worker.run()
    assert not failed, failed

    info = load_project(out.with_suffix(".lkproj")).provenance
    assert info is not None, "the application saved no record of the run"
    assert info["app_version"] == __version__
    assert info["provider"] == "fake"
    assert info["model"] == "fake"
    assert (info["source_lang"], info["target_lang"]) == ("en", "tr")
    assert info["reader"] == "digital"
    assert info["fit_mode"] == "strict"
    assert info["commit"] is None or re.fullmatch(r"[0-9a-f]{40}", info["commit"])

    # ...and the file the user opens carries it as well, not only the project beside it.
    with zipfile.ZipFile(out) as archive:
        entry = next((n for n in archive.namelist() if n.endswith(provenance.FILE_NAME)), None)
        assert entry, archive.namelist()
        assert json.loads(archive.read(entry).decode("utf-8")) == info
