"""The reference list can be kept untranslated from the application, not only from the CLI flag.

`--preserve-references` had no counterpart in the window: someone translating an academic paper
from the desktop application had no way to keep the bibliography out of the model's hands. Both
front ends now read one setting, `translation.preserve_references`, the same arrangement
`fitting.reflow` and `translation.keyword_map_auto` already use, so the two cannot drift apart.

The detection itself is `test_reference_protection.py`'s subject; what these tests pin is the
wiring, and they run the real reader, CLI and writer over a real bibliography rather than checking
that a function was called.
"""

from __future__ import annotations

import sys
from pathlib import Path

from layoutkeep import cli
from layoutkeep.core import tunables
from layoutkeep.core.docir import Block, BlockRole
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker
from layoutkeep.writers.converter import read_any_document

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture

#: One citation entry. Long and specific enough for `is_citation_entry` (bracketed number, volume
#: and page range) that the test is about a reference list and not about a paragraph that happens
#: to mention a year.
CITATION = (
    "[1] Turing, A. M. (1950). Computing Machinery and Intelligence. "
    "Mind, vol. 59, pp. 433-460."
)


def _rewrite(block: Block, text: str) -> None:
    """Replace a block's text, keeping one span: the fixture's markup is not what is under test."""
    line = block.lines[0]
    line.spans = [line.spans[0]]
    line.spans[0].text = text
    block.lines = [line]


def _academic_epub(tmp_path: Path) -> Path:
    """The sample fixture's last chapter turned into a reference list, written to disk.

    Two existing blocks are rewritten rather than a page being appended on purpose: the EPUB writer
    writes the chapters the source manifest declares, so an extra page never reaches the file and a
    test built that way would pass while proving nothing.
    """
    sample = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(sample)

    doc = read_any_document(sample)
    blocks = doc.pages[-1].blocks_in_reading_order()
    heading = blocks[0]
    entry = next(block for block in blocks if block.role is BlockRole.BODY)
    _rewrite(heading, "References")
    _rewrite(entry, CITATION)

    return cli._write_document(doc, sample, tmp_path / "academic.epub")[0]


def _text_of(path: Path) -> str:
    """Everything the written document says, so an assertion does not depend on its structure."""
    return "\n".join(block.text for _, block in read_any_document(path).iter_blocks())


def _run_cli(source: Path, out: Path, *extra: str) -> int:
    args = [
        "translate", str(source), "--from", "en", "--to", "tr",
        "--provider", "fake", "--output", str(out), *extra,
    ]
    return cli.main(args)


def _job(source: Path, out: Path) -> JobConfig:
    return JobConfig(
        input_path=str(source),
        output_path=str(out),
        source_lang="en",
        target_lang="tr",
        provider=ProviderConfig(kind="fake"),
    )


# -- the setting -------------------------------------------------------------------------------


def test_the_setting_exists_and_is_off_by_default() -> None:
    """Off by default: an untouched installation must translate exactly what it did before."""
    spec = tunables.definition("translation.preserve_references")
    assert spec.kind == "bool"
    assert spec.default is False
    assert tunables.get("translation.preserve_references") is False

    # Sitting with the topic map: both are preparation of the document before it is segmented.
    neighbour = tunables.definition("translation.keyword_map_auto")
    assert (spec.section, spec.group) == (neighbour.section, neighbour.group)


# -- the command line --------------------------------------------------------------------------


def test_the_setting_alone_makes_the_cli_preserve_the_bibliography(tmp_path, capsys) -> None:
    """No flag given: if the CLI ignored the setting, the switch in the window would mean
    nothing to the command line, and the two front ends would answer the same question
    differently - which is the drift this setting exists to end."""
    source = _academic_epub(tmp_path)
    out = tmp_path / "cli-on.tr.epub"

    before = tunables.get("translation.preserve_references")
    tunables.set_value("translation.preserve_references", True)
    try:
        assert _run_cli(source, out) == 0
    finally:
        tunables.set_value("translation.preserve_references", before)

    written = _text_of(out)
    assert CITATION in written, "the reference entry came back translated"
    assert "[tr] References" not in written, "the reference heading was translated"
    assert "references" in capsys.readouterr().out, "the run said nothing about the references"


def test_without_the_setting_the_cli_translates_the_bibliography(tmp_path) -> None:
    """The other half of the same fact: the protection is opt-in, and this is what it costs."""
    source = _academic_epub(tmp_path)
    out = tmp_path / "cli-off.tr.epub"

    assert tunables.get("translation.preserve_references") is False
    assert _run_cli(source, out) == 0
    assert f"[tr] {CITATION}" in _text_of(out)


def test_the_flag_on_its_own_still_preserves(tmp_path) -> None:
    """The flag was the only way in before this setting existed; it has to keep working."""
    source = _academic_epub(tmp_path)
    out = tmp_path / "cli-flag.tr.epub"

    assert tunables.get("translation.preserve_references") is False
    assert _run_cli(source, out, "--preserve-references") == 0
    assert "[tr] References" not in _text_of(out)
    assert CITATION in _text_of(out)


# -- the application ---------------------------------------------------------------------------


def test_the_worker_preserves_the_bibliography_when_the_setting_is_on(qtbot, tmp_path) -> None:
    source = _academic_epub(tmp_path)
    out = tmp_path / "app-on.tr.epub"
    worker = TranslationWorker(_job(source, out))
    statuses: list[str] = []
    worker.status.connect(statuses.append)

    before = tunables.get("translation.preserve_references")
    tunables.set_value("translation.preserve_references", True)
    try:
        worker.run()
    finally:
        tunables.set_value("translation.preserve_references", before)

    written = _text_of(out)
    assert CITATION in written, "the worker sent the bibliography to the model"
    assert "[tr] References" not in written
    assert any(line.startswith("references:") for line in statuses), statuses


def test_the_worker_translates_the_bibliography_when_the_setting_is_off(qtbot, tmp_path) -> None:
    """A worker that tagged the blocks unconditionally would pass the test above and take the
    reference list away from everyone who never asked for it."""
    source = _academic_epub(tmp_path)
    out = tmp_path / "app-off.tr.epub"
    worker = TranslationWorker(_job(source, out))
    statuses: list[str] = []
    worker.status.connect(statuses.append)

    assert tunables.get("translation.preserve_references") is False
    worker.run()

    assert f"[tr] {CITATION}" in _text_of(out)
    assert not any(line.startswith("references:") for line in statuses), statuses
