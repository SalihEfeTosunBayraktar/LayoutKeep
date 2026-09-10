"""Literals that must survive translation unchanged.

Style markers (`docir.block_source_text`) keep a translation's *formatting*. This keeps its
*facts*. They are separate problems: a bold run can move within a sentence and still be correct,
whereas a torque figure or a form number that shifts by one character is wrong in a way nobody
may notice until a machine is assembled incorrectly.

Measured need, not a hypothetical. A US tax form read through this pipeline produced 29 segments
that are nothing but digits, plus its OMB identifier, all queued for translation. A machinery
manual carries tolerances like `0.3+0.2 mm` and torques like `34 Nm` inside otherwise ordinary
sentences that do need translating - so the fix cannot simply be "skip this segment".

The approach mirrors the style markers: wrap each protected run in a token, tell the model to
reproduce tokens exactly, then put the original text back. What the model never sees, it cannot
paraphrase. And because the tokens are restored from the source rather than from the reply, a
model that mangles one costs us a review flag rather than a wrong number.

Deliberately conservative. Over-protection is its own failure: fragmenting a sentence into
tokens degrades the translation around them, and a lone `1` protected everywhere would wreck
ordinary prose. These patterns aim at things that are unambiguously data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Marker for a protected literal. Distinct from the numeric style markers (`<0>`), so the two
#: can coexist in one segment without either parser mistaking the other's tokens.
_TOKEN = "{}"
_TOKEN_RE = re.compile("(\\d+)")

#: Patterns for runs that must come back byte-identical. Order matters: the first match wins, so
#: longer and more specific patterns come first.
DEFAULT_PATTERNS: tuple[tuple[str, str], ...] = (
    # Measurement with a tolerance: 0.3+0.2 mm, 8-1 mm, 27 -1 mm, 50 -20 mm.
    ("tolerance", r"\d+(?:[.,]\d+)?\s*[+\-−±]\s*\d+(?:[.,]\d+)?\s*(?:mm|cm|m|in|Nm|N·m|kg|°)\b"),
    # A range written as an inequality: 95 < Y < 100 mm.
    ("range", r"\d+(?:[.,]\d+)?\s*[<>≤≥]\s*[A-Za-z]\s*[<>≤≥]\s*\d+(?:[.,]\d+)?\s*\w*"),
    # A pair sharing one trailing unit: "between 0.05 and 0.2 mm". The first number carries the
    # unit implicitly, so protecting only the second would leave it exposed to being rewritten.
    ("pair", (r"\d+(?:[.,]\d+)?\s*(?:and|to|-|–|ve|ile)\s*\d+(?:[.,]\d+)?\s*"
              r"(?:mm|cm|km|m|in|ft|Nm|N·m|kPa|bar|psi|kg|g|°C|°F|°|%)\b")),
    # Plain measurement or torque: 34 Nm, 0.05 mm, 24.5 Nm, 63 Nm.
    ("measurement", r"\d+(?:[.,]\d+)?\s*(?:mm|cm|km|m|in|ft|Nm|N·m|kPa|bar|psi|kg|g|°C|°F|°|%)\b"),
    # Currency amounts: $200,000, €1.234,56.
    ("currency", r"[$€£₺¥]\s?\d[\d.,]*"),
    # Document and part identifiers: OMB No. 1545-0074, Form W-4, Cat. No. 10220Q.
    ("identifier", r"\b(?:OMB\s+No\.?|Cat\.?\s+No\.?|Form|Ref\.?|P/N|Part\s+No\.?)\s*[\w\-/.]+"),
    # A dotted or hyphenated code with at least one digit: 1545-0074, 00-0288-280.
    ("code", r"\b(?=[\w\-/.]*\d)[A-Z0-9]+(?:[-/.][A-Z0-9]+){2,}\b"),
    # A part number written as space-separated digit groups: "00 0288 280 0". Common on
    # machinery documentation, where the number identifies the exact manual revision.
    ("partnumber", r"\b\d{2,}(?:\s+\d{2,}){2,}(?:\s+\d)?\b"),
    # A measurement whose superscript tolerance OCR flattened: "33* mm", "27-1 mm", "50 =20 mm".
    # Engineering documents write tolerances as superscripts and every OCR engine mangles them
    # differently, so the character between the number and the unit cannot be predicted - which
    # is all the more reason to hand the run through untouched rather than let a model rewrite it.
    ("ocr_tolerance", r"\d+(?:[.,]\d+)?\s*[*=~^±+\-−]\s*\d*\s*(?:mm|cm|m|Nm|N·m|kg|°)\b"),
    # Callout references into a diagram: "the bolts (3)", "the tie rod (1)". Small parenthesised
    # integers only - large ones are more likely to be ordinary numbers in prose. Losing or
    # reordering these sends a reader to the wrong part of the drawing.
    ("callout", r"\((?:[1-9]|[1-9]\d)\)"),
)


@dataclass(slots=True)
class Protection:
    """The protected runs of one segment, and the text with tokens in their place."""

    text: str
    #: Token index -> the exact original substring. Restoration reads from here, never from the
    #: model's reply, so a mangled token cannot corrupt a value.
    literals: dict[int, str] = field(default_factory=dict)
    #: Which pattern matched each index, for reporting which kinds of thing were protected.
    kinds: dict[int, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.literals)


def is_data_only(text: str) -> bool:
    """True when a segment carries no words at all - digits, punctuation and currency only.

    Such a segment has nothing to translate. Sending it wastes a request and invites a model to
    "improve" a number, which is the one thing it must never do.
    """
    stripped = text.strip()
    if not stripped:
        return False
    return not re.search(r"[^\W\d_]", stripped, re.UNICODE)


def protect(text: str, patterns: tuple[tuple[str, str], ...] = DEFAULT_PATTERNS) -> Protection:
    """Replace protected literals with tokens, returning the text and how to restore it."""
    literals: dict[int, str] = {}
    kinds: dict[int, str] = {}
    combined = re.compile(
        "|".join(f"(?P<{name}>{pattern})" for name, pattern in patterns)
    )

    def swap(match: re.Match[str]) -> str:
        index = len(literals)
        literals[index] = match.group(0)
        kinds[index] = match.lastgroup or "unknown"
        return _TOKEN.format(index)

    return Protection(text=combined.sub(swap, text), literals=literals, kinds=kinds)


def restore(text: str, protection: Protection) -> tuple[str, int]:
    """Put the original literals back. Returns the text and how many tokens went missing.

    A missing token means the model dropped or rewrote it, and the value it stood for is simply
    absent from the translation. The caller should flag that segment rather than ship it.
    """
    seen: set[int] = set()

    def put_back(match: re.Match[str]) -> str:
        index = int(match.group(1))
        seen.add(index)
        return protection.literals.get(index, match.group(0))

    result = _TOKEN_RE.sub(put_back, text)
    return result, len(protection.literals) - len(seen)


def describe(protection: Protection) -> str:
    """A short summary of what was protected, for progress output."""
    if not protection.literals:
        return ""
    counts: dict[str, int] = {}
    for kind in protection.kinds.values():
        counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))
