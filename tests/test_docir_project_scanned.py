"""A project remembers which pages were scanned.

`Page.scanned` decides how the writer removes the source text: redaction on a born-digital page,
painting the ink out of the image on a scan. Project files wrote the flag but did not read it back,
so every scanned page drawn from a project - a book redrawn after a writer fix, a document edited
in the review window and exported - went down the born-digital path, where redaction removes
nothing from the image and the translation is drawn over the scanned English. Found through the
lossless audit, which reads projects and audited Electricity in Agriculture's scans as digital.
"""

from __future__ import annotations

from pathlib import Path

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Page, load_project, save_project


def test_a_scanned_page_is_still_scanned_after_a_project_round_trip(tmp_path: Path) -> None:
    block = Block(id="b", role=BlockRole.BODY, bbox=BBox(10, 10, 200, 30))
    doc = Document(pages=[
        Page(number=1, width=259, height=432, blocks=[block], source_ref="0", scanned=True),
        Page(number=2, width=259, height=432, blocks=[], source_ref="1"),
    ])
    path = tmp_path / "book.lkproj"
    save_project(doc, path)
    assert [page.scanned for page in load_project(path).pages] == [True, False]
