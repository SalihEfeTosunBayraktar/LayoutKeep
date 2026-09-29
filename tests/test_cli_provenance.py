"""The command line records, in the file it writes, what translated the document.

The question the record answers - "which version of the application, with what, and with which
methods was this translated?" - is asked about a folder full of outputs, long after the run that
produced them, not about the run the person asking still remembers.

A key must never reach any of it: the record travels inside a document that gets sent on.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pymupdf

from layoutkeep import __version__, cli
from layoutkeep.core import provenance, tunables
from layoutkeep.core.docir import load_project

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture
import build_pdf_fixture

#: Shaped like a real key so a grep over the output would find it if it leaked.
API_KEY = "sk-not-a-real-key-0000"


def _run(capsys, *argv: str) -> str:
    code = cli.main(["translate", *argv])
    printed = capsys.readouterr().out
    assert code == cli.EXIT_OK, printed
    return printed


def test_a_pdf_output_records_the_run_that_made_it(tmp_path: Path, capsys) -> None:
    src = tmp_path / "sample.pdf"
    build_pdf_fixture.build_two_column(src)
    out = tmp_path / "out.tr.pdf"
    project = tmp_path / "run.lkproj"

    tunables.set_value("translation.workers", 3)
    try:
        _run(
            capsys, str(src), "--from", "en", "--to", "tr", "--provider", "fake",
            "--output", str(out), "--api-key", API_KEY, "--save-project", str(project),
        )
    finally:
        tunables.reset("translation.workers")

    info = load_project(project).provenance
    assert info is not None, "the project kept no record of the run"
    assert info["app_version"] == __version__
    assert info["provider"] == "fake"
    assert (info["source_lang"], info["target_lang"]) == ("en", "tr")
    assert info["settings"]["translation.workers"] == 3
    assert info["fit_mode"] == "strict"

    pdf = pymupdf.open(str(out))
    try:
        line = provenance.summary(info)
        assert line in pdf.metadata["producer"], pdf.metadata
        assert line in pdf.metadata["creator"], pdf.metadata
        assert provenance.FILE_NAME in pdf.embfile_names(), pdf.embfile_names()
        embedded = json.loads(pdf.embfile_get(provenance.FILE_NAME).decode("utf-8"))
        written_metadata = json.dumps(pdf.metadata)
    finally:
        pdf.close()

    assert embedded == info
    assert API_KEY not in json.dumps(info)
    assert API_KEY not in json.dumps(embedded)
    assert API_KEY not in written_metadata
    assert API_KEY not in project.read_text(encoding="utf-8")


def test_an_epub_carries_the_record_inside_the_file(tmp_path: Path, capsys) -> None:
    """EPUB→EPUB is an open conversion, so its output has to carry the record too.

    The writer copies every entry through untouched, so the record is an added entry declared in
    the OPF's manifest - part of the book rather than a stray file in the zip.
    """
    src = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(src)
    out = tmp_path / "out.tr.epub"

    _run(capsys, str(src), "--from", "en", "--to", "tr", "--provider", "fake",
         "--output", str(out))

    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
        entry = next((name for name in names if name.endswith(provenance.FILE_NAME)), None)
        assert entry, names
        info = json.loads(archive.read(entry).decode("utf-8"))
        opf = next(name for name in names if name.endswith(".opf"))
        manifest = archive.read(opf).decode("utf-8")

    assert info["app_version"] == __version__
    assert info["provider"] == "fake"
    assert (info["source_lang"], info["target_lang"]) == ("en", "tr")
    assert provenance.FILE_NAME in manifest, manifest

    # The book must still be a book: an item added to the manifest is the one edit this writer
    # makes to the OPF, and getting it wrong (dropping the closing tag, say) leaves a file that
    # nothing can open.
    from layoutkeep.writers.converter import read_any_document

    text = "\n".join(block.text for _, block in read_any_document(out).iter_blocks())
    assert "[tr]" in text, text


def test_the_bilingual_pdf_carries_the_same_record(tmp_path: Path, capsys) -> None:
    """`--dual` writes a second PDF, composed page by page - so it inherits nothing by itself.

    A file that does not say what translated it is the thing the record exists to prevent, and
    this one sits beside the output, where a reader may open it instead.
    """
    src = tmp_path / "sample.pdf"
    build_pdf_fixture.build_two_column(src)
    out = tmp_path / "out.tr.pdf"
    project = tmp_path / "run.lkproj"

    _run(capsys, str(src), "--from", "en", "--to", "tr", "--provider", "fake",
         "--output", str(out), "--save-project", str(project), "--dual", "side")

    info = load_project(project).provenance
    dual = tmp_path / "out.tr.dual.pdf"
    assert dual.is_file(), sorted(p.name for p in tmp_path.iterdir())

    pdf = pymupdf.open(str(dual))
    try:
        assert pdf.metadata["producer"] == provenance.summary(info), pdf.metadata
        assert provenance.FILE_NAME in pdf.embfile_names(), pdf.embfile_names()
        carried = json.loads(pdf.embfile_get(provenance.FILE_NAME).decode("utf-8"))
    finally:
        pdf.close()
    assert carried == info
