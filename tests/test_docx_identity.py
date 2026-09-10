"""The identity test: read a DOCX and write it straight back out with NO translation.

Per the EPUB agent's precedent (docs/CONTRACT.md), this must pass before anything about
translation is reported as working. "Byte-identical" is checked per zip entry on the decompressed
content, since compression parameters aren't part of the document's identity.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_docx_fixture import build_sample_docx

from layoutkeep.readers.docx_reader import read_docx
from layoutkeep.writers.docx_writer import write_docx


def _entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_identity_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "sample.docx"
    build_sample_docx(src)

    doc = read_docx(src)
    out = tmp_path / "out.docx"
    write_docx(doc, src, out)

    src_entries = _entries(src)
    out_entries = _entries(out)

    assert list(src_entries.keys()) == list(out_entries.keys()), "entry order/list changed"

    diffs = {}
    for name, src_data in src_entries.items():
        out_data = out_entries[name]
        if src_data != out_data:
            diffs[name] = (src_data, out_data)

    assert diffs == {}, f"identity round trip differs on: {list(diffs.keys())}"
