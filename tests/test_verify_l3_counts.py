"""L3 must say how much of a block is missing, not just that something is.

WHY THIS EXISTS: `L3 = 20` on the new arXiv run was read - by the night watch and then by a second
reader - as twenty blocks the writer had lost. The count was real; the reading was wrong. L3 fires on
a block whose words are not all on the page, and a block *clipped* at the bottom of its box (the
fitting could not fit a longer target language) and a block that was *never drawn* are two different
faults that used to produce an identical message. The detail now carries `missing of total`, so
`N of N` is a block that is not on the page and anything less is a clipped one.

The partner page here is built by drawing part of the translation onto the source page, which is the
shape the fitting produces when it runs out of room.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).parent))

from test_verify import _ENGLISH, _TURKISH, _source, _translated

from layoutkeep.verify import output_losses

_DETAIL = re.compile(r"^(\d+) of (\d+) words not on the page: ")


def _l3_only(src: Path, out: Path, doc) -> list:
    return [loss for loss in output_losses(src, out, doc) if loss.kind == "L3"]


def test_a_block_that_was_never_drawn_reports_every_word_missing(tmp_path: Path) -> None:
    src = _source(tmp_path / "s.pdf", (100, _ENGLISH))
    doc, _ = _translated(src, _TURKISH)
    out = tmp_path / "o.pdf"
    shutil.copyfile(src, out)  # the page as if the writer drew nothing of the translation

    losses = _l3_only(src, out, doc)

    assert len(losses) == 1
    match = _DETAIL.match(losses[0].detail)
    assert match is not None, f"the detail must carry the counts, got {losses[0].detail!r}"
    missing, total = int(match.group(1)), int(match.group(2))
    assert missing == total > 0, "a block that is not on the page at all is missing every word"


def test_a_clipped_block_reports_how_much_it_lost(tmp_path: Path) -> None:
    """Part of the translation on the page: the fitting ran out of box, not the writer of the block."""
    src = _source(tmp_path / "s.pdf", (100, _ENGLISH))
    doc, _ = _translated(src, _TURKISH)
    out = tmp_path / "o.pdf"

    page_doc = pymupdf.open(src)
    page_doc[0].insert_text((72, 100), "bir bilgi sistemi", fontsize=10)
    page_doc.save(out)
    page_doc.close()

    losses = _l3_only(src, out, doc)

    assert len(losses) == 1
    match = _DETAIL.match(losses[0].detail)
    assert match is not None, f"the detail must carry the counts, got {losses[0].detail!r}"
    missing, total = int(match.group(1)), int(match.group(2))
    assert 0 < missing < total, "a clipped block is missing some of its words, not all of them"
