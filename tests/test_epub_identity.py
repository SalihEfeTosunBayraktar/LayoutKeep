"""The identity test: read an EPUB and write it straight back out with NO translation.

Per .claude/agents/lk-epub.md this must pass before anything about translation is reported as
working. "Byte-identical" is checked per zip entry on the decompressed content (compression
parameters aren't part of the document's identity), plus the mimetype-first/stored requirement.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.writers.epub_writer import write_epub


def _entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_identity_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_sample_epub(src)

    doc = read_epub(src)
    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    src_entries = _entries(src)
    out_entries = _entries(out)

    assert list(src_entries.keys()) == list(out_entries.keys()), "entry order/list changed"

    diffs = {}
    for name, src_data in src_entries.items():
        out_data = out_entries[name]
        if src_data != out_data:
            diffs[name] = (src_data, out_data)

    assert diffs == {}, f"identity round trip differs on: {list(diffs.keys())}"


def test_mimetype_first_and_stored(tmp_path: Path) -> None:
    src = tmp_path / "sample.epub"
    build_sample_epub(src)
    doc = read_epub(src)
    out = tmp_path / "out.epub"
    write_epub(doc, src, out)

    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
