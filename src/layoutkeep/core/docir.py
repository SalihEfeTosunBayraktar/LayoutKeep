"""DocIR - the single intermediate representation every reader produces and every writer consumes.

Design rules (see docs/CONTRACT.md):
  D1  Readers -> DocIR -> Writers. Readers and writers never know about each other.
  D2  The translation layer only sees Segment. It knows nothing about bbox or fonts.
  D4  Phase 1 is Latin-only, but `direction` exists now so no LTR assumption gets hardcoded.
  D5  A Document round-trips through JSON so a job can be saved, edited and re-rendered.

This module must stay dependency-free: no PyMuPDF, no Pillow, no network. Standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class Direction(StrEnum):
    """Writing direction of a run of text."""

    LTR = "ltr"
    RTL = "rtl"


class BlockRole(StrEnum):
    """What a block is, which decides whether and how it gets translated."""

    TITLE = "title"
    HEADING = "heading"
    BODY = "body"
    LIST = "list"
    CAPTION = "caption"
    TABLE = "table"
    FOOTNOTE = "footnote"
    HEADER = "header"          # running page header
    FOOTER = "footer"          # running page footer
    PAGE_NUMBER = "page_number"
    FORMULA = "formula"
    CODE = "code"
    FIGURE = "figure"          # image region, no text
    UNKNOWN = "unknown"


#: Roles whose text is carried through untouched. Translating these damages the document.
NON_TRANSLATABLE_ROLES: frozenset[BlockRole] = frozenset(
    {
        BlockRole.PAGE_NUMBER,
        BlockRole.FORMULA,
        BlockRole.CODE,
        BlockRole.FIGURE,
    }
)


@dataclass(slots=True)
class BBox:
    """Axis-aligned box in PDF user space: origin top-left, y grows downward, unit = point."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def union(self, other: BBox) -> BBox:
        return BBox(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


@dataclass(slots=True)
class Style:
    """Visual appearance of a text run.

    `font_family` is the name as found in the source. It is often a subsetted PDF font that
    lacks the target language's glyphs, so writers resolve it through the font matcher rather
    than using it directly.
    """

    font_family: str = ""
    size: float = 0.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"          # sRGB hex
    background: str | None = None   # None = transparent
    letter_spacing: float = 0.0
    line_height: float | None = None  # None = font default
    #: Font file the fitting stage resolved this style to, once it has checked that the file
    #: actually contains the target language's glyphs. None means "not resolved yet"; writers
    #: then fall back to their own generic family mapping.
    font_path: str | None = None
    #: Whether the source says this run is set in a serif face, when it says so at all - a PDF
    #: font descriptor's serif flag, for instance. None means the source did not say. It is only
    #: a hint for choosing a substitute when the family name is unrecognised (a display face like
    #: "AbrilFatface" is neither in the substitution table nor in any hint list, and without this
    #: it lands on a sans); a recognised name is always believed over it, because producers set
    #: the flag carelessly and it is wrong about as often as it is right on names we do know.
    serif: bool | None = None

    def key(self) -> tuple[Any, ...]:
        """Identity used to decide whether two adjacent runs can be merged into one span."""
        return (
            self.font_family,
            round(self.size, 2),
            self.bold,
            self.italic,
            self.color,
            self.background,
        )


@dataclass(slots=True)
class Span:
    """Smallest unit of uniformly styled text."""

    text: str
    bbox: BBox
    style: Style
    direction: Direction = Direction.LTR


@dataclass(slots=True)
class Line:
    """One visual line. Only readers create these; the fitting stage rebuilds them."""

    spans: list[Span] = field(default_factory=list)
    bbox: BBox | None = None

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass(slots=True)
class Block:
    """A layout region: a paragraph, a heading, a caption, a table cell, ...

    `order` is the reading-order index within the page. Readers must fill it; writers and the
    translation stage rely on it rather than on list position.
    """

    id: str
    role: BlockRole
    bbox: BBox
    lines: list[Line] = field(default_factory=list)
    order: int = 0
    direction: Direction = Direction.LTR
    #: Horizontal text alignment within the block: "left", "center", "right" or "justify".
    #: Readers that see a text layer (PDF) infer it from the block's x-position relative to the
    #: page; readers that see markup (EPUB/DOCX/HTML) resolve it from CSS or paragraph props.
    #: Writers that rebuild a document use it so centred/right-aligned text survives instead of
    #: being flattened to left. Default "left" keeps every pre-existing serialised project valid.
    align: str = "left"
    #: True when this block's text continues into the next block (across a column or page break).
    continues: bool = False
    #: 0.0-1.0. How much the reader trusts this block's text. OCR sets its recogniser score here;
    #: readers with a real text layer leave it at 1.0. Flows into the segment and drives the
    #: review queue, so a shaky OCR line reaches the human instead of being quietly translated.
    confidence: float = 1.0
    #: Set by a reader that already knows this block needs a human eye.
    needs_review: bool = False
    #: Why, in one short phrase for the reviewer. Four different failures raise `needs_review`
    #: - lost inline styling, a literal the model dropped, a glossary term it ignored, a segment
    #: handed back untranslated - and they call for completely different fixes. A flag with no
    #: reason makes the reviewer diff source against target to work out which one happened.
    review_reason: str = ""
    #: Baseline angle in degrees, counter-clockwise, 0 for ordinary horizontal text. Rotated
    #: text is common in real documents - a diagonal watermark, a sideways table header, a
    #: caption running up the margin - and writing it back flat destroys the layout as surely
    #: as losing its font would.
    #:
    #: Note for anyone measuring space: `bbox` stays axis-aligned, so for a rotated block it is
    #: LARGER than the text's real extent. Fitting must account for the angle rather than
    #: treating the bbox as the available room.
    rotation: float = 0.0
    #: The text as it went to the translator, kept when the translation overwrites it. The review
    #: editor shows original and translation side by side (D6), and a saved project must still do
    #: that after being closed and reopened - which it cannot if the source is only in the source
    #: file. Carries the same inline markers as `Segment.source`, so the editor can render the
    #: original's bold and italic runs rather than showing flattened text.
    source_text: str = ""

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def translatable(self) -> bool:
        return self.role not in NON_TRANSLATABLE_ROLES and bool(self.text.strip())

    def dominant_style(self) -> Style:
        """Style covering the most characters. Used when re-rendering a block as a whole."""
        counts: dict[tuple[Any, ...], tuple[int, Style]] = {}
        for line in self.lines:
            for span in line.spans:
                k = span.style.key()
                n, style = counts.get(k, (0, span.style))
                counts[k] = (n + len(span.text), style)
        if not counts:
            return Style()
        return max(counts.values(), key=lambda pair: pair[0])[1]


@dataclass(slots=True)
class ImageRef:
    """A picture on the page, with its bytes, so a writer that rebuilds the document can redraw it.

    Without this DocIR carried text and nothing else. That was invisible while the only PDF
    writer edited a copy of the source - the figures were never removed, so they never had to be
    reproduced. The cross-format writers build a new document from DocIR alone, and every figure
    in the source silently vanished: a 23-image report exported to DOCX or HTML contained none.

    `data` is base64 rather than raw bytes so the project file keeps serialising through
    `asdict`/JSON with no special casing, and so a `.lkproj` stays self-contained - it can be
    re-exported on a machine that no longer has the source document (CONTRACT.md, D5).

    Sayfadaki görselin konumu ve içeriği / A page image's placement and content.
    """

    bbox: BBox
    #: base64-encoded image bytes.
    data: str = ""
    #: Lower-case file extension without the dot: "png", "jpeg", ...
    fmt: str = "png"
    #: Where the picture sat in the document's flow, on the same counter as `Block.order`.
    #: A page-based reader leaves this at -1 and is placed by position instead; a reflowable
    #: one (EPUB) has no positions at all, and without this every picture piled up at the end.
    order: int = -1

    @property
    def data_uri(self) -> str:
        return f"data:image/{self.fmt};base64,{self.data}"


@dataclass(slots=True)
class Page:
    """One page. For EPUB, one source XHTML file maps to one Page."""

    number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    background: str | None = None  # sRGB hex of the page ground, None = white/unknown
    #: Pictures on this page, so writers that rebuild the document can redraw them.
    images: list[ImageRef] = field(default_factory=list)
    #: Reader-specific handle back to the source (PDF page index, EPUB href, ...).
    source_ref: str = ""

    def blocks_in_reading_order(self) -> list[Block]:
        return sorted(self.blocks, key=lambda b: b.order)

    def content_in_reading_order(self) -> list[Block | ImageRef]:
        """Blocks and images together, top to bottom, for writers that rebuild the document.

        Blocks keep the reading order the reader worked out (which handles columns); an image
        has no such order, so each is placed after the blocks that start above it. Good enough
        to keep a figure with the text it belongs to, which is the point - a rebuilt document
        that drops its figures, or piles them all at the end, is not the same document.
        """
        blocks = self.blocks_in_reading_order()
        flow: list[Block | ImageRef] = list(blocks)

        # A picture that knows its place in the flow is put there. This is how a reflowable
        # document (EPUB) works: nothing on the page has a position, so sorting by one put every
        # picture after every block - all of them at the end of the chapter, away from the text
        # they illustrate.
        pending = sorted((i for i in self.images if i.order >= 0), key=lambda i: i.order)
        if pending:
            flow = []
            for index, block in enumerate(blocks):
                while pending and pending[0].order <= index:
                    flow.append(pending.pop(0))
                flow.append(block)
            flow.extend(pending)

        # Everything else is placed by where it sits on the page, which is what a PDF gives us.
        for image in sorted(
            (i for i in self.images if i.order < 0), key=lambda i: (i.bbox.y0, i.bbox.x0)
        ):
            index = sum(1 for b in blocks if b.bbox.y0 <= image.bbox.y0)
            flow.insert(min(index, len(flow)), image)
        return flow


@dataclass(slots=True)
class Document:
    """A whole job. Serialising this is what makes `.lkproj` files work (D5)."""

    pages: list[Page] = field(default_factory=list)
    source_path: str = ""
    source_format: str = ""       # "pdf" | "epub" | "image"
    source_lang: str | None = None
    target_lang: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def iter_blocks(self) -> Iterator[tuple[Page, Block]]:
        for page in self.pages:
            for block in page.blocks_in_reading_order():
                yield page, block


# --------------------------------------------------------------------------------------
# Translation units
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class Segment:
    """One translatable unit handed to a provider.

    This is the ONLY type the provider layer sees (D2). `block_id` is how the result finds its
    way home; providers must return segments with `block_id` untouched.
    """

    block_id: str
    source: str
    target: str = ""
    #: Neighbouring source text given to the model as context. Never translated itself.
    context_before: str = ""
    context_after: str = ""
    #: Soft character budget from the fitting stage. Providers should try to respect it.
    max_len: int | None = None
    #: 0.0-1.0. Readers set OCR confidence; providers may lower it. Drives the review queue.
    confidence: float = 1.0
    needs_review: bool = False
    #: Why this segment was flagged. Carried onto the block so the editor can say it.
    review_reason: str = ""
    #: Set when the text came from the translation memory instead of a provider.
    from_memory: bool = False

    @property
    def translated(self) -> bool:
        return bool(self.target)


def segments_from_document(
    doc: Document,
    *,
    context_blocks: int = 1,
) -> list[Segment]:
    """Flatten a Document into the translatable units a provider consumes.

    `context_blocks` neighbouring blocks are attached as context on each side. Context improves
    pronoun and terminology consistency measurably and costs little, but it is never translated.
    """
    ordered = [b for _, b in doc.iter_blocks() if b.translatable]
    segments: list[Segment] = []
    for i, block in enumerate(ordered):
        before = ordered[max(0, i - context_blocks) : i]
        after = ordered[i + 1 : i + 1 + context_blocks]
        segments.append(
            Segment(
                block_id=block.id,
                source=_original_text(block),
                # Context stays plain: the model reads it, it never has to reproduce it.
                context_before="\n".join(_plain_original(b) for b in before),
                context_after="\n".join(_plain_original(b) for b in after),
                confidence=block.confidence,
                needs_review=block.needs_review,
                review_reason=block.review_reason,
            )
        )
    return segments


def apply_segments(doc: Document, segments: Sequence[Segment]) -> list[str]:
    """Write translated text back onto the document's blocks.

    Returns the ids of segments that could not be matched to a block, so the caller can report
    them instead of silently dropping translations.
    """
    by_id = {b.id: b for _, b in doc.iter_blocks()}
    orphans: list[str] = []
    for seg in segments:
        block = by_id.get(seg.block_id)
        if block is None:
            orphans.append(seg.block_id)
            continue
        if seg.translated and not block.source_text:
            # Capture it before the translation overwrites it, and only the first time: a second
            # pass must not record an already-translated block as its own original. Store the
            # marked form, not `block.text` - the plain text loses which runs were bold or
            # italic, and the editor then shows a flattened original beside a styled translation.
            block.source_text = block_source_text(block)
        if seg.translated and not _replace_block_text(block, seg.target):
            # The block had inline styling and the translation did not bring the markers back,
            # so bold/italic runs inside it were lost. Surface it instead of hiding it.
            seg.needs_review = True
            seg.review_reason = seg.review_reason or "kalın/italik biçimlendirme kayboldu"
        # Carry the segment's verdict onto the block, which is what the review editor reads.
        # Without this every flag raised after the reader ran - a dropped literal, an ignored
        # glossary term, styling lost above, a segment the model handed back untranslated - was
        # set on the segment, and the segment was then thrown away. The review queue only ever
        # showed what the reader itself had flagged.
        if seg.needs_review:
            block.needs_review = True
            block.review_reason = seg.review_reason or block.review_reason
    return orphans


# --------------------------------------------------------------------------------------
# Inline styling across translation
#
# A paragraph is one translation unit, but it can contain bold or italic runs. Sending only the
# plain text loses them. So runs whose style differs from the block's dominant style are wrapped
# in numbered markers - `a <0>bold</0> word` - which the provider is told to carry through
# untouched. The marker index maps back to the original Style, which stays on the block; the
# provider never sees a Style, so this does not break D2.
# --------------------------------------------------------------------------------------

_MARKER_RE = re.compile(r"<(/?)(\d+)>")


def _block_runs(block: Block) -> list[tuple[str, Style | None]]:
    """Flatten a block's spans into (text, style) runs, with a newline run between lines."""
    runs: list[tuple[str, Style | None]] = []
    for i, line in enumerate(block.lines):
        if i:
            runs.append(("\n", None))
        runs.extend((span.text, span.style) for span in line.spans)
    return runs


def _inline_styles(block: Block) -> list[Style]:
    """Styles that differ from the dominant one, in order of first appearance.

    The position in this list is the marker number, so it must be derived the same way when
    building the source text and when applying the translation.
    """
    dominant = block.dominant_style().key()
    styles: list[Style] = []
    seen: set[tuple[Any, ...]] = set()
    for text, style in _block_runs(block):
        if style is None or not text or style.key() == dominant or style.key() in seen:
            continue
        seen.add(style.key())
        styles.append(style)
    return styles


def _original_text(block: Block) -> str:
    """What a provider is handed as the source, on a first pass and on any later one.

    `block.text` holds the translation once a pass has run, so a project reopened to be
    translated again handed the model its own output: with the test provider a second pass
    produced "[tr] [tr] Form W-4", and with a real one a translation of a translation -
    quietly, because nothing about the result looks like an error. `apply_segments` already
    stores the original in `source_text` before overwriting it, in the marked form, so the
    right text was on disk the whole time and simply never read.
    """
    return block.source_text or block_source_text(block)


def _plain_original(block: Block) -> str:
    """The same preference for context, without markers: context is read, never reproduced."""
    return _MARKER_RE.sub("", block.source_text) if block.source_text else block.text


def block_source_text(block: Block) -> str:
    """The text handed to a provider: plain, or with inline markers when the block needs them."""
    plain = block.text
    styles = _inline_styles(block)
    if not styles or _MARKER_RE.search(plain):
        # Nothing to mark, or the text already looks like markers and we would corrupt it.
        return plain
    index = {style.key(): i for i, style in enumerate(styles)}
    dominant = block.dominant_style().key()
    out: list[str] = []
    for text, style in _block_runs(block):
        if style is None or style.key() == dominant:
            out.append(text)
        else:
            n = index[style.key()]
            out.append(f"<{n}>{text}</{n}>")
    return "".join(out)


def _spans_from_marked_text(
    text: str, dominant: Style, styles: list[Style], bbox: BBox, direction: Direction
) -> list[Span] | None:
    """Parse marker syntax back into spans. Returns None if the markers are unusable."""
    spans: list[Span] = []
    stack: list[int] = []
    pos = 0
    matched = False
    for m in _MARKER_RE.finditer(text):
        n = int(m.group(2))
        if n >= len(styles):
            return None
        matched = True
        chunk = text[pos : m.start()]
        if chunk:
            spans.append(Span(chunk, bbox, styles[stack[-1]] if stack else dominant, direction))
        if m.group(1):  # closing marker
            if not stack or stack[-1] != n:
                return None
            stack.pop()
        else:
            stack.append(n)
        pos = m.end()
    if stack or not matched:
        return None
    tail = text[pos:]
    if tail:
        spans.append(Span(tail, bbox, dominant, direction))
    return spans or None


def _replace_block_text(block: Block, text: str) -> bool:
    """Put `text` into `block`. Returns False when inline styling was lost on the way.

    Line breaking is deliberately NOT done here - that is the fitting stage's job, which is the
    only place that can measure text against the real font (D3).
    """
    dominant = block.dominant_style()
    styles = _inline_styles(block)
    spans = None
    if styles:
        spans = _spans_from_marked_text(text, dominant, styles, block.bbox, block.direction)
    faithful = spans is not None or not styles
    if spans is None:
        # K2: bozuk/eksik marker'lari ciktiya ham yazma - temizle, duz metin koy. Bicim kaybi
        # zaten `faithful=False` ile raporlaniyor (apply_segments -> needs_review), ama
        # `<0>BOLUM I.</0>` gibi marker karakterleri okura sizmemeli.
        # Strip unusable markers instead of leaking them raw into the output.
        clean = _MARKER_RE.sub("", text) if styles else text
        spans = [Span(text=clean, bbox=block.bbox, style=dominant, direction=block.direction)]
    block.lines = [Line(spans=spans, bbox=block.bbox)]
    return faithful


# --------------------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------------------


def to_dict(doc: Document) -> dict[str, Any]:
    payload = asdict(doc)
    payload["schema_version"] = SCHEMA_VERSION
    return payload


def from_dict(payload: dict[str, Any]) -> Document:
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported .lkproj schema version {version!r}, this build expects {SCHEMA_VERSION}"
        )
    return Document(
        pages=[_page_from_dict(p) for p in payload.get("pages", [])],
        source_path=payload.get("source_path", ""),
        source_format=payload.get("source_format", ""),
        source_lang=payload.get("source_lang"),
        target_lang=payload.get("target_lang"),
        metadata=dict(payload.get("metadata", {})),
    )


def _page_from_dict(p: dict[str, Any]) -> Page:
    return Page(
        number=p["number"],
        width=p["width"],
        height=p["height"],
        blocks=[_block_from_dict(b) for b in p.get("blocks", [])],
        background=p.get("background"),
        images=[
            ImageRef(
                bbox=BBox(**img["bbox"]),
                data=img.get("data", ""),
                fmt=img.get("fmt", "png"),
                # Absent from every project file written before images knew their place.
                order=img.get("order", -1),
            )
            for img in p.get("images", [])
        ],
        source_ref=p.get("source_ref", ""),
    )


def _block_from_dict(b: dict[str, Any]) -> Block:
    return Block(
        id=b["id"],
        role=BlockRole(b["role"]),
        bbox=BBox(**b["bbox"]),
        lines=[_line_from_dict(ln) for ln in b.get("lines", [])],
        order=b.get("order", 0),
        direction=Direction(b.get("direction", "ltr")),
        continues=b.get("continues", False),
        confidence=b.get("confidence", 1.0),
        needs_review=b.get("needs_review", False),
        review_reason=b.get("review_reason", ""),
        source_text=b.get("source_text", ""),
        rotation=b.get("rotation", 0.0),
    )


def _line_from_dict(ln: dict[str, Any]) -> Line:
    return Line(
        spans=[_span_from_dict(s) for s in ln.get("spans", [])],
        bbox=BBox(**ln["bbox"]) if ln.get("bbox") else None,
    )


def _span_from_dict(s: dict[str, Any]) -> Span:
    return Span(
        text=s["text"],
        bbox=BBox(**s["bbox"]),
        style=Style(**s["style"]),
        direction=Direction(s.get("direction", "ltr")),
    )


def save_project(doc: Document, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(to_dict(doc), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_project(path: str | Path) -> Document:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
