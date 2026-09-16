"""Geometry helpers shared by the readers.

`_infer_alignment` started in `pdf_reader.py` and is pure geometry - no pymupdf, no DocIR
beyond BBox - so both readers can use it. It lives here rather than being imported across,
because `pdf_reader` already imports `image_reader` (to hand it a rasterised page) and reaching
back the other way would close the loop.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Line, Span


def infer_alignment(bbox: BBox, page_width: float) -> str:
    """Infer a block's horizontal alignment from its x-position relative to the page.

    A centred block sits roughly symmetric around the page midline; a right-aligned block sits
    close to the right margin while a left-aligned one hugs the left. Thresholds are generous so
    full-width justified paragraphs (which span most of the page) are not misread as centred.
    Only applies to blocks that leave a real margin on at least one side, so a block that already
    fills the page stays "left"/justify rather than being guessed at.
    """
    if page_width <= 0:
        return "left"
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


#: Characters that can stand in for a word-break hyphen in a scanned or typeset line:
#: hyphen-minus, soft hyphen, and the two Unicode hyphens.
_HYPHENS = "-­‐‑"


def join_hyphenation(lines: list[Line]) -> None:
    """Merge `hyphen-` + `ation` at a line break into `hyphenation`, in place.

    Only applies when the break looks like a genuine word split: the line ends in a hyphen
    directly after a letter, and the next line starts with a lowercase letter.
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
        next_spans = lines[i + 1].spans
        if not next_spans or not next_spans[0].text or not next_spans[0].text[0].islower():
            i += 1
            continue
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
