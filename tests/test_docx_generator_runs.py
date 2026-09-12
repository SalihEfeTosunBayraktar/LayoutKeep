"""A translated block that carries inline styled runs (bold/italic spans) must keep them
in a generated DOCX.

Found by the real-model verification run on rich_report.pdf (2026-09-12): pdf->pdf kept
9/9 styled runs (it edits the file in place), pdf->docx kept 7/9. The generator wrote only
the block's *dominant* style over the whole paragraph, so a paragraph containing a bold run
inside plain text came out all-plain. The matrix's identity run never saw it because its
fixture paragraph held its runs inside a single dominant style too.

Measure: docs/samples/format_matrix.json is blind here; this test reads the runs back out
of the generated OOXML directly.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Direction,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.writers.docx_generator import generate_docx_from_docir


def _span(text: str, bold: bool = False, italic: bool = False) -> Span:
    return Span(
        text=text,
        bbox=BBox(0, 0, 100, 10),
        style=Style(bold=bold, italic=italic, size=11.0),
        direction=Direction.LTR,
    )


def _doc_with_mixed_runs() -> Document:
    """One body paragraph: plain + bold + plain + italic + plain - the shape a real
    translation round-trip leaves in the block after marker parsing."""
    block = Block(
        id="p0#0",
        role=BlockRole.BODY,
        bbox=BBox(0, 0, 400, 100),
    )
    block.lines = [
        Line(spans=[
            _span("Bu kelime "),
            _span("kalın", bold=True),
            _span(" ve bu da "),
            _span("italik", italic=True),
        ])
    ]
    page = Page(number=1, width=595, height=842, blocks=[block], source_ref="0")
    return Document(pages=[page])


def _runs(path: Path) -> list[tuple[bool, bool, str]]:
    """(bold, italic, text) for every run in the generated document.xml, in order."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "replace")
    runs: list[tuple[bool, bool, str]] = []
    for m in re.finditer(r"<w:r>(.*?)</w:r>", xml, re.S):
        body = m.group(1)
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", body, re.S))
        bold = "<w:b/>" in body
        italic = "<w:i/>" in body
        if text:
            runs.append((bold, italic, text))
    return runs


def test_inline_bold_italic_runs_survive_generation(tmp_path: Path) -> None:
    out = tmp_path / "out.docx"
    generate_docx_from_docir(_doc_with_mixed_runs(), out)

    runs = _runs(out)
    styles = {(b, i) for b, i, _ in runs}

    assert (True, False) in styles, f"no bold run in output: {runs}"
    assert (False, True) in styles, f"no italic run in output: {runs}"
    # The plain segments must stay plain - not inherit the bold of a neighbouring run.
    assert (False, False) in styles, f"plain run lost: {runs}"

    bold_texts = [t for b, _, t in runs if b]
    assert any("kalın" in t for t in bold_texts), f"'kalın' is not bold in output: {runs}"
    italic_texts = [t for _, i, t in runs if i]
    assert any("italik" in t for t in italic_texts), f"'italik' is not italic in output: {runs}"


def test_whole_block_bold_stays_bold(tmp_path: Path) -> None:
    """A single-span bold block (a table header cell) must not come out plain either."""
    block = Block(id="p0#0", role=BlockRole.BODY, bbox=BBox(0, 0, 400, 100))
    block.lines = [Line(spans=[_span("Hücre", bold=True)])]
    page = Page(number=1, width=595, height=842, blocks=[block], source_ref="0")

    out = tmp_path / "out.docx"
    generate_docx_from_docir(Document(pages=[page]), out)

    runs = _runs(out)
    assert runs and runs[0][0], f"bold block came out plain: {runs}"
