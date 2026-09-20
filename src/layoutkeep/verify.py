"""Is the translated document lossless? Checked on what was written, and repaired where it can be.

The loss criteria were defined and measured in the translation campaign (docs/campaign/JOURNAL.md)
and used to live only in `tools/audit/lossless_audit.py`, so a document translated in the
application got none of it: what the campaign reached after its repair rounds was not what a user
received. They live here now, and the CLI and the desktop worker run them after writing.

    L1  same pages                 output page count == source page count
    L2  nothing left untranslated  blocks still in the source language, or in a third one
    L3  nothing dropped by writer  translated blocks whose words are missing from their page
    L4  nothing off the page       words outside the page box
    L5  no markup leaked           tags in the output that are not in the source
    L6  no numbers lost            numbers of the source missing from the translation
    L7  nothing over other text    words of one block drawn over another's
    L8  nothing untouched moved    on born-digital pages, text no translated block covers moved
    L9  no garbled letters         a word of the translation mixing in another alphabet's letter

`verify_and_repair` asks again for what a translation lost (L2, L6, L9) - a reply in the wrong
language or without a number is intermittent, so a later request often comes back right - and
flags everything still lost for review, with the reason, so the review queue shows exactly where
the output departs from the source.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from layoutkeep.core.copies import (
    drops_numbers,
    garbled_words,
    is_copy,
    is_identical,
    ordinary_words,
    wrong_language,
)
from layoutkeep.core.docir import Block, Document, Segment, apply_segments
from layoutkeep.core.protect import is_data_only

#: A block counts as present on its page when this share of its words are found there. Below 1.0
#: because the renderer may hyphenate a long word across a line break, which splits one token in
#: two.
_PRESENT_SHARE = 0.9

_MARKUP = re.compile(r"</?[A-Za-z][A-Za-z0-9_]*\s*/?>|<\d+>|</\d+>|</?text\b", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_INLINE_MARKER = re.compile(r"</?\d+>")

#: Two words from different lines overlapping by more than this share of the smaller one cannot
#: both be read. Measured: a magazine page with blocks drawn over each other had 17 such pairs; a
#: clean novel page, a contents page, a scanned book page and the source PDF itself had 0.
_OVERLAP_SHARE = 0.3

#: Height below which a drawn word is not legible text in the first place.
_LEGIBLE_PT = 5.0

#: Blocks with fewer ordinary words than this are too short to call untranslated without knowing
#: the language: a name and an untranslated two-word phrase look the same.
_MIN_PROSE_WORDS = 4

LOSS_KINDS = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10")

LABELS = {
    "L1": "page count differs",
    "L2": "left untranslated",
    # "dropped by the writer" was the first name and it was wrong: the check finds a block whose
    # words are not on the page, and the common cause is not a dropped block but one the fitting
    # could not fit - drawn, clipped at its box, and flagged. PLOS's math paragraphs are all of
    # them: the reader merged a page of formulas into one 79pt "line", nothing could fit that, and
    # the audit reported eight "dropped" blocks that were on the page, cut short.
    "L3": "text not on the page",
    "L4": "drawn off the page",
    "L5": "markup leaked",
    "L6": "numbers lost",
    "L7": "text drawn over text",
    "L8": "untouched text moved",
    "L9": "garbled letters",
    "L10": "text drawn over a figure",
}

#: What the review queue says, in the application's language like every other review reason.
REVIEW_REASONS = {
    "L1": "doğrulama: çıktının sayfa sayısı farklı",
    "L2": "doğrulama: çevrilmemiş ya da başka bir dilde",
    "L3": "doğrulama: bloğun metni sayfada bulunamadı (çizilmedi ya da kutusunda kırpıldı)",
    "L4": "doğrulama: metin sayfanın dışına taştı",
    "L5": "doğrulama: çıktıya etiket sızdı",
    "L6": "doğrulama: çeviride sayılar kayboldu",
    "L7": "doğrulama: metin başka bir metnin üstüne yazıldı",
    "L8": "doğrulama: çevrilmeyen metin yerinden oynadı",
    "L9": "doğrulama: çeviride başka bir alfabeden harf karıştı",
    "L10": "doğrulama: metin bir görselin üstüne yazıldı",
}

#: The losses a new request to the model can mend. The rest are drawn wrong, not translated wrong.
_ASK_AGAIN = frozenset({"L2", "L6", "L9"})


@dataclass(frozen=True)
class Loss:
    kind: str
    #: Index of the page in `Document.pages`, or -1 for the document as a whole.
    page: int
    detail: str
    block_ids: tuple[str, ...] = ()


def source_of(block: Block) -> str:
    """The text the block had before translation, without inline markers."""
    return _INLINE_MARKER.sub("", block.source_text) if block.source_text else block.text


def is_checked(block: Block) -> bool:
    """A block whose words the criteria judge: translatable prose, not data, not a wordless scrap."""
    from layoutkeep.core.docir import BlockRole
    from layoutkeep.writers.pdf_writer import is_wordless

    if block.role == BlockRole.BIBLIOGRAPHY:
        return False
    return block.translatable and not is_data_only(source_of(block)) and not is_wordless(block)


def is_untouched(block: Block) -> bool:
    return not block.source_text or is_identical(source_of(block), block.text)


def words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text.replace("­", ""))]


def translation_losses(doc: Document, target_lang: str | None) -> list[Loss]:
    """L2, L6 and L9, block by block, on the text as written."""
    losses: list[Loss] = []
    for index, page in enumerate(doc.pages):
        for block in page.blocks:
            if not is_checked(block):
                continue
            source, written = source_of(block), block.text
            # Prose is judged on ordinary words (core.copies): names, brands, addresses and
            # quoted strings legitimately survive translation and must not count against it.
            if len(ordinary_words(source)) >= _MIN_PROSE_WORDS:
                wrong = wrong_language(written, target_lang) if target_lang else None
                if is_untouched(block) or wrong or is_copy(source, written):
                    losses.append(Loss("L2", index, written[:90], (block.id,)))
            if block.source_text and drops_numbers(source, written, target_lang or ""):
                losses.append(Loss("L6", index, written[:90], (block.id,)))
            if block.source_text and garbled_words(source, written):
                losses.append(Loss("L9", index, written[:90], (block.id,)))
    return losses


def output_losses(source_pdf: Path, output_pdf: Path, doc: Document) -> list[Loss]:
    """L1, L3, L4, L5, L7 and L8, on the written PDF against its source."""
    import pymupdf

    losses: list[Loss] = []
    with pymupdf.open(str(source_pdf)) as source, pymupdf.open(str(output_pdf)) as output:
        if source.page_count != output.page_count:
            losses.append(
                Loss("L1", -1, f"{source.page_count} source pages, {output.page_count} output")
            )
        source_markup = {
            m.group(0).casefold() for page in source for m in _MARKUP.finditer(page.get_text())
        }
        for index, page_data in enumerate(doc.pages):
            try:
                number = int(page_data.source_ref)
            except ValueError:
                continue
            if number >= output.page_count or number >= source.page_count:
                continue
            losses.extend(_page_losses(source[number], output[number], page_data, index, source_markup))
    return losses


def _page_losses(source_page, page, page_data, index: int, source_markup: set[str]) -> list[Loss]:
    losses: list[Loss] = []
    rect = page.rect
    drawn = page.get_text("words")
    on_page = Counter(w for word in drawn for w in words(word[4]))

    for word in drawn:
        x0, y0, x1, y1 = word[:4]
        if x1 < rect.x0 - 1 or x0 > rect.x1 + 1 or y1 < rect.y0 - 1 or y0 > rect.y1 + 1:
            losses.append(Loss("L4", index, repr(word[4])))

    pairs, involved = overlapping_words(drawn, as_in=source_page.get_text("words"))
    if pairs:
        owners = tuple(sorted({
            block.id for x, y in involved
            if (block := _block_at(page_data.blocks, x, y)) is not None
        }))
        losses.append(Loss("L7", index, f"{pairs} overlapping word pairs", owners))

    over_figure = words_over_figures(page, drawn, as_in=source_page.get_text("words"))
    if over_figure:
        owners = tuple(sorted({
            block.id for x, y in over_figure
            if (block := _block_at(page_data.blocks, x, y)) is not None
        }))
        losses.append(Loss("L10", index, f"{len(over_figure)} words drawn on a figure", owners))

    text = page.get_text()
    for match in _MARKUP.finditer(text):
        if match.group(0).casefold() not in source_markup:
            owners = tuple(b.id for b in page_data.blocks if match.group(0) in b.text)
            losses.append(Loss("L5", index, repr(match.group(0)), owners))

    if not page_data.scanned:
        moved = kept_text_moved(source_page, page, page_data)
        if moved:
            owners = tuple(sorted({
                block.id for r in moved
                if (block := _block_at(page_data.blocks, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)) is not None
            }))
            losses.append(Loss("L8", index, f"{len(moved)} untouched text runs moved", owners))

    for block in page_data.blocks:
        if not is_checked(block):
            continue
        written = words(block.text)
        # An unchanged block on a scanned page is not drawn: its text is the scan's pixels, and the
        # invisible layer holds whatever that page's own OCR read there.
        if not written or (page_data.scanned and is_untouched(block)):
            continue
        need = Counter(written)
        present = sum(min(n, on_page[w]) for w, n in need.items())
        if present / sum(need.values()) < _PRESENT_SHARE:
            losses.append(Loss("L3", index, block.text[:90], (block.id,)))
    return losses


def _block_at(blocks: Sequence[Block], x: float, y: float) -> Block | None:
    for block in blocks:
        b = block.bbox
        if b.x0 - 2 <= x <= b.x1 + 2 and b.y0 - 2 <= y <= b.y1 + 2:
            return block
    return None


#: Share of the page an image must cover before it is the page's own background rather than a
#: figure. A scan is one big image with the translation written over it by design.
_FIGURE_SHARE = 0.85

#: Share of a drawn word's box that must fall inside a figure before it is unreadable there.
_ON_FIGURE_SHARE = 0.55


def _union_area(rects: list) -> float:
    """Area covered by at least one of `rects`, exactly, by sweeping x-strips."""
    edges = sorted({edge for rect in rects for edge in (rect.x0, rect.x1)})
    total = 0.0
    for left, right in pairwise(edges):
        if right <= left:
            continue
        spans = sorted(
            (rect.y0, rect.y1) for rect in rects if rect.x0 < right and rect.x1 > left
        )
        height = 0.0
        top: float | None = None
        bottom: float | None = None
        for span_top, span_bottom in spans:
            if bottom is None or span_top > bottom:
                if bottom is not None and top is not None:
                    height += bottom - top
                top, bottom = span_top, span_bottom
            else:
                bottom = max(bottom, span_bottom)
        if bottom is not None and top is not None:
            height += bottom - top
        total += (right - left) * height
    return total


#: How close a drawn word must be to a source word of the same figure to be that source word's
#: translation rather than a stray: a few points, since the type size may differ slightly.
_LABEL_TOLERANCE = 3.0


def words_over_figures(
    page, drawn: Sequence[Sequence], *, as_in: Sequence[Sequence] | None = None
) -> list[tuple[float, float]]:
    """Centres of the drawn words that sit on a figure, for L10.

    Found late and expensively: a Wikipedia page reached the site with 87 words of Turkish lying
    across a photograph, and L7 - which only compares text against text - reported nothing. The
    cause is geometric rather than linguistic (a block's bounding box wraps *around* a picture, so
    the re-flowed translation runs straight over it), which is why it needs its own look at the
    written page rather than another comparison of strings.

    Two rules keep the number about *this* run, both learned from documents that scored nonzero:

    * The page's images are judged together, not one by one. The 1907 cookbook's pages carry the
      scan twice plus a dozen patches over the printed lines, none above 6% of the page on its
      own, so no image looked like a background - and 126 words were reported "over a figure" on a
      page where every word is on the scan by design. Their union covers the page, which is what
      says the page is a scan.
    * A figure's own labels are text the source drew there. The held-out arXiv page reported 26
      words over a bar chart whose values and category names are text on the plot in the original;
      its source page counts 28 of the same. `as_in` is the source page's words, and a word drawn
      where the source already had one over that figure is the figure's content.
    """
    import pymupdf  # lazy, like `output_losses`: this module stays importable without it

    page_area = max(1.0, page.rect.get_area())
    images = [pymupdf.Rect(info["bbox"]) for info in page.get_image_info()]
    if _union_area(images) >= _FIGURE_SHARE * page_area:
        return []
    figures = [rect for rect in images if rect.get_area() < _FIGURE_SHARE * page_area]
    if not figures:
        return []

    labels: list[tuple[float, float]] = []
    for word in as_in or ():
        box = pymupdf.Rect(word[:4])
        centre = ((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
        for figure in figures:
            overlap = box.intersect(figure)
            if overlap.is_valid and overlap.get_area() > _ON_FIGURE_SHARE * box.get_area():
                labels.append(centre)
                break

    found: list[tuple[float, float]] = []
    for word in drawn:
        box = pymupdf.Rect(word[:4])
        for figure in figures:
            overlap = box.intersect(figure)
            if not (overlap.is_valid and overlap.get_area() > _ON_FIGURE_SHARE * box.get_area()):
                continue
            centre = ((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            if any(
                abs(centre[0] - x) <= _LABEL_TOLERANCE and abs(centre[1] - y) <= _LABEL_TOLERANCE
                for x, y in labels
            ):
                break  # the source's own label, redrawn where it was
            found.append(centre)
            break
    return found


def overlapping_words(
    drawn: list, *, same_block: bool = False, as_in: list | None = None
) -> tuple[int, list[tuple[float, float]]]:
    """Pairs of words from different lines drawn over each other, and the centres of those words.

    `same_block=False` counts words of different text blocks - one text drawn over another (L7).
    `same_block=True` counts lines of one block squeezed into each other - text forced into a box
    far too small, typically recognition noise from a decorative advert.

    `as_in` is the source page's words. An overlap the source page already has is the source's own
    typesetting, not something drawn over it, and is not counted: an equation's superscript over
    its subscript (held-out arXiv 2609.19145, 11 such pairs on one untouched equation), and a
    footnote set inside the box of the line it belongs to (arXiv 2507.03009, where a footnote box
    sits inside a footer's - translating one and not the other redrew a word over a word that had
    always been there).

    A pair is judged against the source by *position*, not by text: each drawn word is matched to
    the source word standing where it stands, whatever that word says, and the pair counts only
    when the two source words did not overlap each other.
    """
    import pymupdf

    source_boxes: list[pymupdf.Rect] = [pymupdf.Rect(w[:4]) for w in (as_in or [])]
    as_set: dict[str, list[tuple[float, float]]] = {}
    for word in as_in or []:
        as_set.setdefault(word[4], []).append((word[0], word[1]))

    def source_overlapped(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
        """Were the source words at `a` and `b` already drawn over each other?

        Each drawn word must also lie *inside* the source word standing where it is: a word drawn
        over a glyph, wider than the box it covers, is new text laid over existing text however
        much the two source boxes overlapped. Without that, a translation drawn across an equation
        would be excused by the equation's own overlapping superscript and subscript.
        """
        if not source_boxes:
            return False
        first = _at(source_boxes, a)
        second = _at(source_boxes, b)
        if first is None or second is None:
            return False
        if not (_inside(a, first) and _inside(b, second)):
            return False
        inter = first & second
        if inter.is_empty:
            return False
        smaller = min(first.get_area(), second.get_area())
        return smaller > 0 and inter.get_area() / smaller > _OVERLAP_SHARE

    def untouched(word) -> bool:
        return any(
            abs(x - word[0]) <= 1.0 and abs(y - word[1]) <= 1.0
            for x, y in as_set.get(word[4], ())
        )

    # Only legible words count: text under _LEGIBLE_PT tall is already below the readability floor,
    # and two such scraps touching is not one text drawn over another.
    boxes = sorted(
        (
            (pymupdf.Rect(w[:4]), w[5], (w[5], w[6]), untouched(w))
            for w in drawn
            if len(w[4]) > 1 and (w[3] - w[1]) >= _LEGIBLE_PT
        ),
        key=lambda item: item[0].y0,
    )
    pairs = 0
    involved: list[tuple[float, float]] = []
    for i, (a, block_a, line_a, set_a) in enumerate(boxes):
        for b, block_b, line_b, set_b in boxes[i + 1:]:
            if b.y0 >= a.y1:
                break  # sorted by top: nothing further down can reach into `a`
            if line_a == line_b or (block_a == block_b) != same_block or (set_a and set_b):
                continue
            inter = a & b
            if inter.is_empty:
                continue
            smaller = min(a.get_area(), b.get_area())
            if smaller > 0 and inter.get_area() / smaller > _OVERLAP_SHARE:
                if source_overlapped(a, b):
                    continue
                pairs += 1
                involved += [((a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2), ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)]
    return pairs, involved


def _at(boxes: list, rect) -> object | None:
    """The source box that covers `rect`'s centre, if any - the word that stood here."""
    centre = ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    for box in boxes:
        if box.x0 - 2 <= centre[0] <= box.x1 + 2 and box.y0 - 2 <= centre[1] <= box.y1 + 2:
            return box
    return None


#: Share of a drawn word that must lie inside the source word standing where it is, before the
#: pair can be excused as the source's own typesetting. A translation drawn over a glyph spills
#: out of it (measured: a 50pt word over a 38pt equation glyph, 57% contained); a word the source
#: set there is inside its own box by definition.
_INSIDE_SHARE = 0.8


def _inside(drawn, source) -> bool:
    """Is `drawn` mostly within `source`? A word that spills out of it is not the word that was there."""
    inter = drawn & source
    if inter.is_empty:
        return False
    area = drawn.get_area()
    return area > 0 and inter.get_area() / area >= _INSIDE_SHARE


def kept_text_moved(source_page, output_page, page_data) -> list:
    """Text the pipeline did not translate that is not where it was.

    Nothing the pipeline did not translate should move. Think Python's Figure 3.1 did - redaction
    elsewhere on the page shifted 8 of its 11 labels.

    Compared word by word. A run split differently by the renderer - the source's `OCR` plus a
    superscript `4` come back as one word `OCR4`, on arXiv 2507.03009's comparison table - is the
    same text in the same place, and reading it as a move said damaged where nothing had.
    """
    import pymupdf

    changed = [
        pymupdf.Rect(b.bbox.x0 - 2, b.bbox.y0 - 2, b.bbox.x1 + 2, b.bbox.y1 + 2)
        for b in page_data.blocks
        if b.translatable and not (b.source_text and source_of(b).split() == b.text.split())
    ]

    def runs(page) -> list[tuple[str, pymupdf.Rect]]:
        return [
            (word[4].strip(), pymupdf.Rect(word[:4]))
            for word in page.get_text("words")
            if word[4].strip()
        ]

    out = runs(output_page)
    moved = []
    for text, rect in runs(source_page):
        if any(r.intersects(rect) for r in changed):
            continue
        # Half a word of the run's own height: a kept block redrawn because a neighbour's clearing
        # reached it lands a point or two off (NIST's author names, 2-3 pt), which is not damage;
        # Figure 3.1's labels dropped 10-11 pt, a whole line.
        tolerance = max(1.0, rect.height / 2)
        if not any(
            t == text and abs(o.x0 - rect.x0) <= tolerance and abs(o.y0 - rect.y0) <= tolerance
            for t, o in out
        ):
            moved.append(rect)
    return moved


@dataclass
class VerifyReport:
    """What verification found, what asking again mended, and what was left flagged."""

    rounds: int = 0
    repaired: int = 0
    remaining: Counter = field(default_factory=Counter)
    checked_blocks: int = 0

    @property
    def lossless(self) -> bool:
        return not sum(self.remaining.values())


def verify_and_repair(
    doc: Document,
    segments: Sequence[Segment],
    *,
    target_lang: str | None,
    write: Callable[[], None],
    source_pdf: Path | None = None,
    output_pdf: Path | None = None,
    ask_again: Callable[[list[Segment]], int] | None = None,
    refit: Callable[[list[Segment]], None] | None = None,
    rounds: int = 2,
) -> VerifyReport:
    """Check the written document, ask again for what a translation lost, flag what remains.

    The document must already be written. `write()` writes it again after a repair; `ask_again`
    re-requests segments in place and returns how many came back mended (`providers.retry`);
    `refit` fits the re-requested segments to their boxes again (PDF). The output checks run when
    `source_pdf` and `output_pdf` are given, i.e. for PDF to PDF.
    """
    report = VerifyReport(checked_blocks=sum(1 for _, b in doc.iter_blocks() if is_checked(b)))
    by_block = {s.block_id: s for s in segments}

    def find() -> list[Loss]:
        found = translation_losses(doc, target_lang)
        if source_pdf is not None and output_pdf is not None:
            found += output_losses(source_pdf, output_pdf, doc)
        return found

    losses = find()
    while losses and ask_again is not None and report.rounds < rounds:
        wanted = {bid for loss in losses if loss.kind in _ASK_AGAIN for bid in loss.block_ids}
        again = [by_block[bid] for bid in sorted(wanted) if bid in by_block]
        if not again:
            break
        report.rounds += 1
        mended = ask_again(again)
        if not mended:
            break
        report.repaired += mended
        if refit is not None:
            refit(again)
        apply_segments(doc, again)
        write()
        losses = find()

    flag_losses(doc, segments, losses)
    report.remaining = Counter(loss.kind for loss in losses)
    return report


def flag_losses(doc: Document, segments: Sequence[Segment], losses: Sequence[Loss]) -> None:
    """Raise the review flag, with the reason, on every block a loss names."""
    blocks = {b.id: b for _, b in doc.iter_blocks()}
    by_block = {s.block_id: s for s in segments}
    for loss in losses:
        for block_id in loss.block_ids:
            reason = REVIEW_REASONS[loss.kind]
            block = blocks.get(block_id)
            if block is not None:
                block.needs_review = True
                block.review_reason = _joined(block.review_reason, reason)
            segment = by_block.get(block_id)
            if segment is not None:
                segment.needs_review = True
                segment.review_reason = _joined(segment.review_reason, reason)


def _joined(existing: str, reason: str) -> str:
    if not existing:
        return reason
    return existing if reason in existing else f"{existing}; {reason}"
