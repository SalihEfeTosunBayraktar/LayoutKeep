"""Turning one parsed reply text into the outbound Segment.

Çözümlenmiş yanıt metnini temizleyip çıkış Segment'ine dönüştürür: uydurulmuş etiketleri
atar, kaybolan liste etiketini geri koyar, eksik yanıtı incelemeye işaretler.
Cleans a parsed reply text and builds the outbound Segment.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Segment

#: An opening, closing or self-closing tag with a name - any name, in any script.
_ANY_TAG = re.compile(r"</?\s*([^\W\d][\w-]*)(?:\s[^<>]*)?/?>", re.UNICODE)


#: A list label at the start of a text: "3.", "12)", "1.4.", "a.", "b)", "(1)", "(b)". A space may be
#: missing before a letter - Turkish statutes set "4.Kapsama" - but not before a digit, so a year or a
#: decimal ("2012 yılında", "3.5 m") is never taken for a label.
_LEADING_LABEL = re.compile(
    r"^\s*((?:\d+(?:\.\d+)*[.)])|(?:[a-z][.)])|(?:\((?:\d{1,2}|[a-z])\)))(?:\s|(?=[^\W\d_]))"
)


def with_leading_label(source: str, reply: str) -> str:
    """Put back a list label the source starts with and the reply lost.

    A list number is the list's structure, not text to translate - and the model drops it: a Think
    Python exercise came back without "3." through three repair rounds.
    """
    match = _LEADING_LABEL.match(source)
    if match is None:
        return reply
    label = match.group(1)
    if reply.lstrip().startswith(label):
        return reply
    return f"{label} {reply.lstrip()}"


def without_invented_tags(source: str, reply: str) -> str:
    """Remove every named tag the source does not itself contain.

    A model formatting a reply invents tags named after anything - "</vagon>" (Turkish for
    "wagon") reached a page of Electricity in Agriculture, after "<br/>" and "</text" had each been
    handled by name. What decides it is the source: a tag it contains is content, any other is not.
    The numeric style markers (<0>...</0>) have no name and are never touched.
    """
    allowed = {m.group(0) for m in _ANY_TAG.finditer(source)}
    cleaned = _ANY_TAG.sub(lambda m: m.group(0) if m.group(0) in allowed else "", reply)
    return " ".join(cleaned.split())


def apply_result(seg: Segment, target: str | None) -> Segment:
    """Build the outbound Segment for one input segment.

    `target is None` means the model never returned this id (refused, dropped it, or the
    reply stayed unparsable after the repair attempt) - marked for review, never filled in
    from the source text.
    """
    if target:
        target = with_leading_label(seg.source, without_invented_tags(seg.source, target))
    return Segment(
        block_id=seg.block_id,
        source=seg.source,
        target=target or "",
        context_before=seg.context_before,
        context_after=seg.context_after,
        max_len=seg.max_len,
        confidence=seg.confidence,
        needs_review=target is None,
        # K1: model bu id'yi dondurmediyse sebep yazilmali / review must say why
        review_reason=(
            "REVIEW_PROVIDER_EMPTY"
            if target is None
            else ""
        ),
        from_memory=False,
    )
