"""Reading a model's reply: the {id: text} map, why it was unreadable, whether markers match.

Model yanıtını okur: {id: metin} eşlemesi, okunamama nedeni ve işaretçilerin tutup tutmadığı.
Reads a model reply as leniently as measured runs require, and never guesses content.
"""

from __future__ import annotations

import json
import re
from collections import Counter

#: Matches the numbered inline-style markers DocIR wraps around a run, e.g. `<0>` / `</0>`.
#: This layer never learns what a marker means (D2) - it only has to carry the token through.
_MARKER_RE = re.compile(r"<(/?)(\d+)>")

#: HTML the model sometimes formats a reply with ("<br/>" on NIST page 34). The source reached it
#: as plain text, so no such tag is content. A break becomes a space; other tags are dropped. The
#: numeric style markers (<0>...</0>) do not match.
_HTML_BREAK = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_HTML_TAG = re.compile(
    r"</?\s*(?:p|b|i|u|em|strong|span|div|sup|sub|small|font)(?:\s[^>]*)?/?>", re.IGNORECASE
)

#: A tag named after a field of the reply format, which the model sometimes wraps or closes a
#: value with ("...sunmaktadir.</text" on book page 251). No document text is written this way,
#: and the inline style markers are numeric (<0>...</0>), so these are never content.
_FIELD_TAG = re.compile(r"</?\s*(?:text|id)\s*/?(?:>|$)", re.IGNORECASE)

#: A backslash that begins no JSON escape: not a quote, backslash, slash, b f n r t, or u + 4 hex.
_LONE_BACKSLASH = re.compile(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})')


def markers_match(source: str, target: str) -> bool:
    """True when `target` carries exactly the same multiset of markers as `source`.

    Word order changes across languages, so this checks the marker set, not its position.
    """
    return Counter(_MARKER_RE.findall(source)) == Counter(_MARKER_RE.findall(target))


def why_unreadable(reply: str) -> str:
    """The parser's complaint about a reply, with the text around the fault - never the whole reply."""
    try:
        data = json.loads(_LONE_BACKSLASH.sub(r"\\\\", reply))
    except json.JSONDecodeError as exc:
        start = max(exc.pos - 40, 0)
        return f"{exc.msg} at character {exc.pos}: {reply[start:exc.pos + 40]!r}"
    if not isinstance(data, list):
        return f"a {type(data).__name__}, not a list: {reply[:80]!r}"
    return f"an item without id and text: {reply[:80]!r}"


def _decode_reply(reply: str) -> object:
    """The JSON in a reply, read as leniently as the replies measured in held-out runs require.

    - A backslash that starts no JSON escape - a set-minus copied from inline math (arXiv
      2609.19145) - made the whole reply unreadable, the same way on every retry; it is read as
      the literal character it is.
    - Items written one after another instead of inside a list (NASA scan: "Extra data at character
      392") are read as that list.
    Returns None when nothing readable is there.
    """
    for candidate in (reply, _LONE_BACKSLASH.sub(r"\\\\", reply)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        items = _json_sequence(candidate)
        if items is not None:
            return items
    return None


def _json_sequence(text: str) -> list | None:
    """Two or more JSON values written one after another (separated by whitespace or commas)."""
    decoder = json.JSONDecoder()
    text = text.strip()
    values, position = [], 0
    while position < len(text):
        try:
            value, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            return None
        values.append(value)
        while position < len(text) and text[position] in " \t\r\n,":
            position += 1
    return values if len(values) > 1 else None


def parse_reply(reply: str) -> dict[str, str] | None:
    """Parse a model reply into {id: translated_text}. Returns None if it isn't the expected
    JSON array of {id, text} objects - the caller treats that as a malformed reply."""
    data = _decode_reply(reply)
    if isinstance(data, dict) and "id" in data and "text" in data:
        # Asked for one segment, a model may answer with the item itself rather than a list of one
        # (held-out Wikipedia "Photosynthesis": logged as "a dict, not a list", paragraph lost).
        data = [data]
    if not isinstance(data, list):
        return None
    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            return None
        text = _HTML_BREAK.sub(" ", str(item["text"]))
        text = _HTML_TAG.sub("", _FIELD_TAG.sub("", text))
        result[str(item["id"])] = " ".join(text.split())
    return result
