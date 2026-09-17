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
from fixtures.build_pdf_fixture import build_two_column


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env_script = str(Path(sys.executable).with_name("python"))
    return subprocess.run(
        [env_script, "-m", "layoutkeep.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def test_cli_refuses_a_locked_conversion(tmp_path: Path) -> None:
    """EPUB to PDF is locked in this build (the reflow generators are not ready - see
    docs/ENGINE-ARCHITECTURE.md), and the command line has to say so rather than write a file
    the interface would not have produced. EPUB→EPUB itself is open now, so the refusal has to
    be exercised on a genuinely locked target."""
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    out = tmp_path / "out.tr.pdf"

    result = _run_cli(
        "translate", str(src), "--to", "tr", "--from", "en",
        "--provider", "fake", "--output", str(out),
    )
    assert result.returncode != 0
    assert "not enabled" in (result.stderr + result.stdout)
    assert not out.exists(), "a refused conversion must not leave a file behind"


def test_cli_translates_a_pdf_end_to_end(tmp_path: Path) -> None:
    """The conversion this build is for, run the whole way through the command line."""
    src = tmp_path / "sample.pdf"
    build_two_column(src)
    out = tmp_path / "out.tr.pdf"

    result = _run_cli(
        "translate", str(src), "--to", "tr", "--from", "en",
        "--provider", "fake", "--output", str(out),
    )
    assert result.returncode == 0, result.stderr

    pdf = pymupdf.open(str(out))
    assert pdf.page_count >= 1
    full_text = "".join(pdf[p].get_text() for p in range(pdf.page_count))
    assert "[tr]" in full_text, "the translation reached the page"
    # The written output is checked, and what the check finds is reported (layoutkeep/verify.py).
    assert "verify    " in result.stdout, result.stdout
