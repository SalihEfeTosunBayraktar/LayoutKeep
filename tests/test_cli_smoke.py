"""End-to-end smoke test: run the real CLI (fake provider) over the fixture EPUB.

The unit tests prove each tier in isolation; this proves the wiring — that `cli translate`
actually reads a document, segments it, hands it to a provider, writes the target, and that the
target re-opens as the same structure. The fake provider is deterministic and network-free, so
this runs fast and pins the whole pipeline without a model server.

README's own warning applies: passing tests are weak evidence. This one exists to catch the
class of defect where a format pair silently drops content in the real pipeline even though
each reader/writer passes alone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.readers.epub_reader import read_epub


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env_script = str(Path(sys.executable).with_name("python"))
    return subprocess.run(
        [env_script, "-m", "layoutkeep.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def test_cli_translate_epub_to_epub(tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    out = tmp_path / "out.tr.epub"

    result = _run_cli(
        "translate", str(src), "--to", "tr", "--from", "en",
        "--provider", "fake", "--output", str(out),
    )
    assert result.returncode == 0, result.stderr

    # Output re-opens with the same spine and non-empty translated blocks.
    doc = read_epub(out)
    assert [p.source_ref for p in doc.pages] == ["chap1.xhtml", "chap2.xhtml"]
    chapter = next(b for p in doc.pages for b in p.blocks if b.text.strip() == "[tr] Chapter One")
    assert chapter is not None


def test_cli_translate_epub_to_pdf(tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    out = tmp_path / "out.tr.pdf"

    result = _run_cli(
        "translate", str(src), "--to", "tr", "--from", "en",
        "--provider", "fake", "--output", str(out),
    )
    assert result.returncode == 0, result.stderr

    pdf = pymupdf.open(str(out))
    assert pdf.page_count >= 1
    full_text = "".join(pdf[p].get_text() for p in range(pdf.page_count))
    # The chapter heading made it into the PDF as translated text.
    assert "[tr] Chapter One" in full_text
