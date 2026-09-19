"""Geometry helpers shared by the readers.

`_infer_alignment` started in `pdf_reader.py` and is pure geometry - no pymupdf, no DocIR
beyond BBox - so both readers can use it. It lives here rather than being imported across,
because `pdf_reader` already imports `image_reader` (to hand it a rasterised page) and reaching
back the other way would close the loop.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import BBox, Line, Span


def infer_alignment(bbox: BBox, page_width: float, lines: list[BBox] | None = None) -> str:
    """Infer a block's horizontal alignment from its x-position relative to the page.

    A centred block sits roughly symmetric around the page midline; a right-aligned block sits
    close to the right margin while a left-aligned one hugs the left. Thresholds are generous so
    full-width justified paragraphs (which span most of the page) are not misread as centred.
    Only applies to blocks that leave a real margin on at least one side, so a block that already
    fills the page stays "left"/justify rather than being guessed at.
    """
    if page_width <= 0:
        return "left"
    boxes = [box for box in (lines or []) if box is not None]
    if len(boxes) >= 2:
        return _alignment_from_lines(boxes, page_width)
    left_margin = bbox.x0
    right_margin = page_width - bbox.x1
    block_center = (bbox.x0 + bbox.x1) / 2.0
    page_center = page_width / 2.0

    # A block that spans nearly the whole page is justified/full-width, not centred.
    span = bbox.x1 - bbox.x0
    if span >= page_width * 0.8:
        return "left"

    # Centred: the block's middle sits near the page's middle, with balanced margins.
    if abs(block_center - page_center) <= page_width * 0.05 and min(left_margin, right_margin) > 0:
        return "center"
    # Right-aligned: hugged to the right edge, and genuinely pushed there - the space to its
    # left is larger than the block itself. Comparing the left margin with a fraction of the
    # PAGE instead called a narrow page's body column right-aligned: 318pt wide with its text
    # from x=74 to x=307 leaves an 11pt right margin and a 74pt left one, and the full-width
    # guard above only fires at 80% of the page against that column's 73%. Measured over six
    # pages of computer-systems-Architecture.pdf, 55 of 192 blocks came out "right" and 25 of
    # those were prose over 80 characters long.
    #
    # A folio in the right margin is 20pt wide with 280pt to its left; a column of prose is
    # 233pt wide with 74pt to its left. The margin being larger than the text is what "pushed
    # to the right" means, and it scales with the page instead of guessing at it.
    if right_margin <= page_width * 0.05 and left_margin > span:
        return "right"
    return "left"


def _alignment_from_lines(boxes: list[BBox], page_width: float) -> str:
    """Alignment read from how a block's lines line up, not from where the block sits.

    Justified or flush-left lines share a left edge; centred lines share a centre and not a left
    edge; right-aligned lines share a right edge. A block's position on the page cannot tell a
    column of prose in the middle of a narrow page from a centred title - the digital pilot's novel
    and textbook came out with every paragraph centred - but its lines can.

    From three lines on, the first line is not required to share the left edge: a first-line
    indent is a paragraph, not a different alignment.
    """
    tolerance = max(2.0, page_width * 0.015)

    def spread(values: list[float]) -> float:
        return max(values) - min(values)

    lefts = [box.x0 for box in boxes]
    if spread(lefts[1:] if len(boxes) >= 3 else lefts) <= tolerance:
        return "left"
    if spread([box.x1 for box in boxes]) <= tolerance:
        return "right"
    if spread([(box.x0 + box.x1) / 2 for box in boxes]) <= tolerance:
        return "center"
    return "left"


#: Characters that can stand in for a word-break hyphen in a scanned or typeset line:
#: hyphen-minus, soft hyphen, and the two Unicode hyphens.
_HYPHENS = "-­‐‑"

#: A word that may legitimately be split across a line break: letters only, hyphen at the end.
#: A token carrying a slash, a colon, a dot or a digit is a URL, a path or an identifier, where
#: the hyphen belongs to the text: `.../docs/api-` + `reference/chat/create` joined into
#: `.../docs/apireference/chat/create` on arXiv 2507.03009, eating a hyphen that was part of the
#: link, and fusing two rows into one line 2.4x the width of either - which then ran over the
#: footnote beside it (L7, a page that had no overlap came back with one).
_WORD_FRAGMENT = re.compile(r"[^\W\d_]+-", re.UNICODE)


def _continues_the_column(above, below) -> bool:
    """Does `below` continue the column `above` was set in?

    A hyphenated continuation begins at the same left edge, or further left where the paragraph's
    next line starts at the margin - so `below` may start left of `above`, but not to its right,
    which would put it in another column beside it.

    An overlap of the two boxes is *not* required. A paragraph's last line is short: `(Von Gizy-`
    ending at the right of a column is continued by `cki; Montgomery).` at the left margin, and
    the two boxes share no width at all. Requiring it split a name in two on arXiv 2507.03009
    (`fresh_pdfmt` chunk_0000).
    """
    if above is None or below is None:
        return True  # nothing measured: let the other guards decide
    return below.x0 <= above.x0 + 2.0


def join_hyphenation(lines: list[Line]) -> None:
    """Merge `hyphen-` + `ation` at a line break into `hyphenation`, in place.

    Only applies when the break looks like a genuine word split: the line ends in a hyphen
    directly after a letter, the token ending in that hyphen is a word rather than a URL, path or
    identifier, the next line starts with a lowercase letter, and it continues the same column.
    """
    i = 0
    while i < len(lines) - 1:
        spans = lines[i].spans
        if not spans or not spans[-1].text:
            i += 1
            continue
        last_span = spans[-1]
        tail = last_span.text
        if len(tail) < 2 or tail[-1] not in _HYPHENS or not tail[-2].isalpha():
            i += 1
            continue
        if not _WORD_FRAGMENT.fullmatch(tail.split()[-1]):
            i += 1
            continue  # a URL, a path or an identifier: the hyphen is part of the text
        next_spans = lines[i + 1].spans
        if not next_spans or not next_spans[0].text or not next_spans[0].text[0].islower():
            i += 1
            continue
        if not _continues_the_column(lines[i].bbox, lines[i + 1].bbox):
            i += 1
            continue  # a continuation starts where the line above started, not in another column
        # Only the word fragment moves up. Folding the whole next line into this one - which
        # this did - left the merged line with its one-line box, so the block's box stopped a
        # line short and the writer never painted out the source line under it (book pages 28
        # and 451: "ing term it represents is A'BC'D." visible under the translation).
        head = next_spans[0]
        fragment, _, remainder = head.text.partition(" ")
        spans[-1] = Span(text=tail[:-1] + fragment, bbox=last_span.bbox, style=last_span.style)
        if remainder.strip():
            next_spans[0] = Span(text=remainder.lstrip(), bbox=head.bbox, style=head.style)
        else:
            del next_spans[0]
        if not next_spans:
            # The next line was nothing but the fragment: its box now belongs to this line.
            below = lines[i + 1].bbox
            if below is not None:
                lines[i].bbox = below if lines[i].bbox is None else lines[i].bbox.union(below)
            del lines[i + 1]
        i += 1
