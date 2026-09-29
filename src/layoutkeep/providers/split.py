"""Cut a segment the model would not translate into pieces small enough that it will.

WHY THIS EXISTS. `retry_untranslated` already asks again for a segment that came back as its own
source - once in the leftovers' own small batch, then three times alone - and one paragraph still
survives every held-out document: one on IRS Publication 505, one on the 1895 mushroom book, one
on the Sherlock Holmes EPUB, seven on arXiv 2609.19145. The ladder changes the request's company
and context, never its *size*, and a whole paragraph is what the model echoes.

Measured in this project's own journal: a dialogue paragraph on The Time Machine echoed in the main
pass and in the batch retry, yet translated 24 times out of 24 when sent on its own; four exercise
items came back in English 3 times out of 3 with their neighbouring context and translated 3 times
out of 3 without it. What the failed attempts have in common is the shape of the request, so the
last resort changes it: the text is cut at its own sentence and list boundaries and each piece is
asked for alone.

WHAT IS PRESERVED. The separators are the source's own - the spaces, the line breaks between list
items, the break after a bullet - and they are put back verbatim. Reassembling cannot lose a line
break or glue two items together, and no piece is ever replaced by anything but its own reply.
Nothing here paraphrases, reorders or drops: a piece that comes back unusable makes the whole
attempt fail, and the caller keeps what it had.

Deliberately conservative about when to cut. A block of one sentence, a table cell, a heading and
anything already short are left alone - splitting them buys nothing and costs a request each.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: Where the text may be cut: after sentence-ending punctuation, after the punctuation that joins
#: two list items or clauses on one line, and at every line break. The separator itself is kept.
_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+|\n+")

#: Fewer words than this and a piece is not worth a request of its own: "5.2.1" or "(a)" would be
#: sent, answered and reassembled for nothing, and a fragment that short carries no context for the
#: model to translate from anyway.
_MIN_PIECE_WORDS = 2

#: More pieces than this and the block is a list of scraps rather than prose: the assembled result
#: would be stitched from a dozen independent replies, which is the point at which per-piece
#: translation stops being a repair and starts inventing a document.
_MAX_PIECES = 12


@dataclass(frozen=True, slots=True)
class Piece:
    """One unit of a cut segment, with the source's own separator around it."""

    #: The text to ask for, as it stood between its neighbours.
    text: str
    #: Whitespace that followed this piece in the source, reproduced verbatim when reassembling.
    following: str = ""
    #: Whitespace that preceded it. Only the first piece can carry any.
    leading: str = ""


def pieces(
    source: str,
    *,
    max_pieces: int = _MAX_PIECES,
    min_words: int = _MIN_PIECE_WORDS,
) -> list[Piece]:
    """Cut `source` into the pieces to ask for one by one. Empty when cutting would not help.

    Returns [] for text that is already one unit (a heading, a table cell, a short label), for
    text whose pieces would be too short to translate, and for text that cuts into more pieces
    than `max_pieces` - a caller that gets [] keeps what it had.
    """
    if max_pieces < 2:
        return []
    cut: list[Piece] = []
    start = 0
    # Whitespace seen with no text on either side of it. It belongs to the piece before it, and is
    # handed on when that piece is the last one so the source's trailing space survives.
    pending = ""
    for match in _BOUNDARY.finditer(source):
        body = source[start:match.start()]
        start = match.end()
        if not body.strip():
            pending += body + match.group(0)
            continue
        if cut and pending:
            cut[-1] = Piece(cut[-1].text, cut[-1].following + pending, cut[-1].leading)
        pending = ""
        cut.append(Piece(body, match.group(0)))
    tail = source[start:]
    if tail.strip():
        cut.append(Piece(tail))
    elif cut:
        cut[-1] = Piece(cut[-1].text, cut[-1].following + pending + tail, cut[-1].leading)
    elif pending or tail:
        return []  # nothing but whitespace: there is no text here to translate

    if len(cut) < 2 or len(cut) > max_pieces:
        return []
    if any(len(piece.text.split()) < min_words for piece in cut):
        return []
    if cut:
        leading = source[: len(source) - len(source.lstrip())]
        cut[0] = Piece(cut[0].text, cut[0].following, leading)
    return cut


def reassemble(replies: Sequence[str], cut: Sequence[Piece]) -> str:
    """Put the pieces' replies back in the source's own separators. One reply per piece."""
    if len(replies) != len(cut):
        raise ValueError(f"{len(replies)} replies for {len(cut)} pieces")
    out = []
    for index, (reply, piece) in enumerate(zip(replies, cut, strict=True)):
        out.append((piece.leading if index == 0 else "") + reply.strip() + piece.following)
    return "".join(out)
