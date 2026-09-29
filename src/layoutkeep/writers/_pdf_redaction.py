"""Clearing the source text while keeping form fields and links, and judging what changed.

Kaynak metni silerken form alanlarını ve bağlantıları korur; neyin değiştiğine karar verir.
"""

from __future__ import annotations

import re

import pymupdf

from layoutkeep.core.docir import Block
from layoutkeep.writers._pdf_writer_common import _ROTATION_EPS, _rect

#: Letters per character, below which a block carries no words and is left as scanned.
#:
#: OCR reads a Karnaugh map or a truth table correctly character by character but has no idea
#: the digits form a grid, so it returns one block per horizontal run. Re-typesetting that run
#: as a line of prose destroys the figure: page 28 of `computer-systems-Architecture.pdf` came
#: back with `{123`, `{14576` and `1112131514 A 108` where its maps had been.
#:
#: OCR confidence cannot tell these apart - `1112131514 A 108` is reported at 1.00, because the
#: recognition is right and it is the two-dimensional structure that is lost. What does tell
#: them apart is words. Measured over that page's 34 blocks, the grid fragments run 0.00 to 0.18
#: letters per character and the real text ('(a) Two-variable map', 'adjacent squares') 0.50 to
#: 1.00, with nothing in between.
#:
#: Such a block has nothing to translate - protection already answers it with its own source -
#: so redrawing it cannot improve it, and measurably makes it worse.
_MIN_WORDINESS = 0.3

_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


#: How thin a drawing is to be a link's underline, and how near the link's bottom edge it runs.
_UNDERLINE_MAX_HEIGHT = 1.2
_UNDERLINE_EDGE = 2.0


def link_underlines(page: pymupdf.Page, changed: list[Block]) -> list[pymupdf.Rect]:
    """The underlines of links inside blocks whose words are replaced, as areas to clear.

    A browser prints a link's underline as a thin rectangle along the link's bottom edge. Once the
    words above it are redrawn in another language the line marks nothing and runs through the new
    text. Only such a line goes - thin, along a link's bottom edge, inside a changed block - so a
    rule, a fraction bar or a table border stays.
    """
    links = [pymupdf.Rect(link["from"]) for link in page.get_links()]
    boxes = [_rect(block.bbox) + pymupdf.Rect(-2, -2, 2, 2) for block in changed
             if abs(block.rotation) <= _ROTATION_EPS]
    if not links or not boxes:
        return []
    found: list[pymupdf.Rect] = []
    for drawing in page.get_drawings():
        line = drawing["rect"]
        if line.height > _UNDERLINE_MAX_HEIGHT or line.width < 2:
            continue
        under_link = any(
            abs(line.y1 - link.y1) <= _UNDERLINE_EDGE
            and min(line.x1, link.x1) - max(line.x0, link.x0) >= 0.5 * line.width
            for link in links
        )
        if under_link and any(box.contains(line) for box in boxes):
            found.append(line + pymupdf.Rect(-0.5, -0.5, 0.5, 0.5))
    return found


def is_wordless(block: Block) -> bool:
    """True when a block carries essentially no letters, only digits and punctuation.

    Judged on the source text where there is one (`Block.source_text`, set when a translation
    overwrites the block), because the question is whether this block ever had words to
    translate - not what came back. A grid of digits answered with a grid of digits would read
    the same either way, but a reply that arrived as prose would otherwise talk the writer into
    re-typesetting a figure it should have left alone.
    """
    text = (block.source_text or block.text).strip()
    if not text:
        return True
    return len(_LETTER_RE.findall(text)) / len(text) < _MIN_WORDINESS


def redact_keeping_forms(page: pymupdf.Page, areas: list, *, line_art: bool = False) -> None:
    """Remove the text under `areas`, without disturbing forms the redaction did not touch.

    Applying redactions makes MuPDF rewrite the page, and it substitutes a rewritten copy for every
    form XObject on it - even one no area touches. In that copy text can move: Think Python's Figure
    3.1 had 8 of 11 labels up to 11 pt lower after redacting the running header 150 pt above it.
    So each rewritten form is restored from the original, and the restoration kept only if nothing
    the areas were meant to remove has come back with it.
    """
    document = page.parent
    before = page.get_xobjects()
    for area in areas:
        page.add_redact_annot(area, cross_out=False, fill=None)
    # `line_art` removes the drawings the areas cover and keeps the text (a link's underline).
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=(pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if line_art
                  else pymupdf.PDF_REDACT_LINE_ART_NONE),
        text=pymupdf.PDF_REDACT_TEXT_NONE if line_art else pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    after = page.get_xobjects()
    if not areas or len(before) != len(after):
        return
    pairs = _pair_forms(before, after)
    rects = [area.rect if isinstance(area, pymupdf.Quad) else pymupdf.Rect(area) for area in areas]

    def removed_text_is_back() -> bool:
        for word in page.get_text("words"):
            middle = pymupdf.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)
            if any(rect.contains(middle) for rect in rects):
                return True
        return False

    for original, rewritten in pairs:
        if original == rewritten:
            continue
        saved_object = document.xref_object(rewritten)
        saved_stream = document.xref_stream(rewritten)
        try:
            # The whole object at once: `xref_copy` sets key by key, and a value holding a path -
            # pdfLaTeX's `/PTEX.FileName (./vocab_venn5.pdf)` on every included figure - was parsed
            # as a key path and raised, taking the whole page with it (held-out arXiv 2609.19145).
            document.update_object(rewritten, document.xref_object(original))
            document.update_stream(rewritten, document.xref_stream(original))
        except (pymupdf.mupdf.FzErrorBase, RuntimeError, ValueError):
            # A form that cannot be restored keeps MuPDF's rewrite: text inside it may sit a little
            # off, which verification reports (L8), rather than the page being lost.
            document.update_object(rewritten, saved_object)
            document.update_stream(rewritten, saved_stream)
            continue
        if removed_text_is_back():
            document.update_object(rewritten, saved_object)
            document.update_stream(rewritten, saved_stream)


def _pair_forms(before: list, after: list) -> list[tuple[int, int]]:
    """Each original form's xref with the xref of MuPDF's rewrite of it, matched by the form's box.

    Not by position: the rewrite lists the forms in another order than the page did. On PLOS ONE's
    first page the positional pairing put the 'Check for updates' badge into another form's slot -
    278 drawings became 3 and a large green arc was drawn in their place. A form whose box is not
    unique on both sides is left out, so it keeps MuPDF's rewrite, which draws correctly.
    """
    def by_box(xobjects: list) -> dict:
        boxes: dict = {}
        for xref, _name, _stream, box in xobjects:
            boxes.setdefault(tuple(round(v, 2) for v in box), []).append(xref)
        return {box: xrefs[0] for box, xrefs in boxes.items() if len(xrefs) == 1}

    old, new = by_box(before), by_box(after)
    return [(old[box], new[box]) for box in old if box in new]


def _unchanged(block: Block) -> bool:
    """The written text is the source exactly - letter case included, since a change of case is
    a change on the page. Markers and whitespace are not compared.

    A block with no `source_text` was never translated: the pipeline records the original only
    when a segment came back translated (`apply_segments`), so an empty one means the text on the
    block is still the source - the batch it was in failed, or it was never sent. Reading that as
    "changed" redrew those blocks in a substitute face for nothing, and a redrawn block is laid
    out from its own box's left edge: arXiv 2507.03009's footer URL came back 82pt left of where
    the source set it, over the footnote beside it (L7).
    """
    if not block.source_text:
        return True
    return same_text(block.source_text, block.text)


def same_text(source: str, written: str) -> bool:
    """The same words, markers and whitespace aside - the test for "this block needs no redrawing"."""

    def plain(text: str) -> str:
        return " ".join(re.sub(r"</?\d+>", "", text).split())

    return plain(source) == plain(written)
