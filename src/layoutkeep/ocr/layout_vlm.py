"""Ask a vision model what each region of a scanned page IS.

Geometry stays with the detector and the text stays with the recogniser; this answers only the
question the heuristics could not. Every rule that tried to tell a heading from a formula from a
running header worked off one number - the height of the detected box - and every one of them
was calibrated on a single page and broke another:

  * a displayed equation, `F(A, B, C, D) = SUM (0, 2, 8, ...)`, has a tall box because of the
    sigma and the subscripts, so it was promoted to a heading and redrawn at 9.00pt instead of
    ~6.3pt - text that grew for no reason;
  * a running header sharing its line with a large folio ("38 CHAPTER ONE Digital Logic
    Circuits") came out at 9.57pt for the same reason.

Two attempts to recover the real type size from the pixels failed under measurement, and both
are recorded here so they are not tried again: the median ink-band height over column strips
measures stroke fragments rather than glyph bands (0.96pt for a 6pt line), and rapidocr's word
boxes all inherit the line band, so a large folio and the small caps beside it come back the
same height (10.56pt against 10.80pt).

A vision model shown the page with its regions numbered gets all of this right. Measured on page
54 of `computer-systems-Architecture.pdf`: the folio labelled `page_number`, the header
`running_header`, and all three displayed equations `formula` - in one request, 603 prompt and
298 completion tokens.

It is optional and fail-safe. Without a server, or on any malformed reply, `classify` returns an
empty mapping and the caller keeps whatever it had decided: a page read slightly wrong is better
than a page not read at all.
"""

from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageDraw

from layoutkeep.core.docir import BlockRole

#: What the model is allowed to answer, mapped onto DocIR roles. `formula` and `page_number` are
#: non-translatable in DocIR, so labelling them correctly also stops equations and folios from
#: being sent to a translator at all.
LABEL_TO_ROLE: dict[str, BlockRole] = {
    "running_header": BlockRole.HEADER,
    "running_footer": BlockRole.FOOTER,
    "body": BlockRole.BODY,
    "heading": BlockRole.HEADING,
    "formula": BlockRole.FORMULA,
    "caption": BlockRole.CAPTION,
    "table": BlockRole.TABLE,
    "figure_label": BlockRole.FIGURE,
    "page_number": BlockRole.PAGE_NUMBER,
}

#: How the model may describe a region's type size relative to the page's body text. Used to
#: stop a tall box dictating a large font: a region the model calls `same` or `smaller` keeps the
#: page's body size however tall its detected box happens to be.
SIZES = frozenset({"smaller", "same", "larger"})

#: Width the page is sent at. Large enough to read the type, small enough that the image stays a
#: few hundred KB rather than several MB - the model is being asked what the regions are, not to
#: read them.
RENDER_WIDTH = 900

#: How many regions are listed in the prompt. The whole page is shown either way; this caps the
#: text listing so a dense page cannot push the prompt out of a modest context window.
MAX_LISTED = 60

_PROMPT = (
    "This is a scanned page from a printed book. Each red box is numbered.\n"
    "For each number, say what that region IS, choosing exactly one label from:\n"
    "running_header, running_footer, body, heading, formula, caption, table, figure_label, "
    "page_number.\n\n"
    "Also say whether the region's TYPE SIZE is smaller, same or larger than the page's body "
    "text.\n\n"
    "Regions (recognised text, truncated):\n{listing}\n\n"
    'Answer ONLY as JSON: [{{"n":1,"label":"...","size":"smaller|same|larger"}}, ...] '
    "for regions 1 to {count}."
)


@dataclass(frozen=True, slots=True)
class RegionVerdict:
    """What the model said about one region."""

    role: BlockRole
    size: str


class ChatFn(Protocol):
    """Sends one vision request and returns the assistant's text.

    Injected rather than built in, so the classifier is testable without a server and a caller
    can route it through whatever transport it already has.
    """

    def __call__(self, prompt: str, image_png: bytes) -> str: ...


def annotate(image: Image.Image, boxes: list[tuple[float, float, float, float]]) -> bytes:
    """The page with its regions outlined and numbered, as PNG bytes.

    The numbers are what the model answers about, so one is drawn inside its box when there is no
    room to the left - a number off the edge of the canvas is a region the model cannot refer to.
    """
    scale = RENDER_WIDTH / image.width if image.width > RENDER_WIDTH else 1.0
    view = (
        image.resize((int(image.width * scale), int(image.height * scale)))
        if scale != 1.0
        else image.copy()
    )
    draw = ImageDraw.Draw(view)
    for index, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        box = [x0 * scale, y0 * scale, x1 * scale, y1 * scale]
        draw.rectangle(box, outline=(255, 0, 0), width=2)
        label_x = box[0] - 16 if box[0] > 18 else box[0] + 2
        draw.text((label_x, box[1]), str(index), fill=(255, 0, 0))
    buffer = io.BytesIO()
    view.save(buffer, format="PNG")
    return buffer.getvalue()


def classify(
    image: Image.Image,
    boxes: list[tuple[float, float, float, float]],
    texts: list[str],
    chat: ChatFn,
) -> dict[int, RegionVerdict]:
    """Label each region, keyed by its 1-based number.

    Returns an empty mapping when the model cannot be reached or answers something unusable; the
    caller then keeps its own classification rather than losing the page.
    """
    if not boxes:
        return {}
    listing = "\n".join(f"{i}: {t[:52]!r}" for i, t in enumerate(texts[:MAX_LISTED], start=1))
    prompt = _PROMPT.format(listing=listing, count=min(len(boxes), MAX_LISTED))
    try:
        reply = chat(prompt, annotate(image, boxes))
    except (OSError, urllib.error.URLError, ValueError, RuntimeError, KeyError):
        return {}
    return parse(reply)


def parse(reply: str) -> dict[int, RegionVerdict]:
    """Read the model's JSON, ignoring anything around it and any entry that is not usable.

    Forgiving about the wrapper - a model that answers inside a ```json fence is answering
    correctly - and strict about the content: an unknown label is dropped rather than guessed at,
    because a wrong role is worse than no role.
    """
    match = re.search(r"\[.*]", reply, re.DOTALL)
    if not match:
        return {}
    try:
        entries = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(entries, list):
        return {}

    verdicts: dict[int, RegionVerdict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        number, label = entry.get("n"), entry.get("label")
        if not isinstance(number, int) or label not in LABEL_TO_ROLE:
            continue
        size = entry.get("size")
        verdicts[number] = RegionVerdict(
            role=LABEL_TO_ROLE[label],
            size=size if size in SIZES else "same",
        )
    return verdicts


def openai_vision_chat(base_url: str, model: str, timeout: float = 900.0) -> ChatFn:
    """A `ChatFn` talking to an OpenAI-compatible server that accepts images.

    `reasoning_effort` is sent for the same reason the translation transport sends it: this is a
    look-and-label task, and a reasoning model otherwise spends hundreds of tokens describing how
    it intends to look before it looks.
    """

    def chat(prompt: str, image_png: bytes) -> str:
        payload = {
            "model": model,
            "temperature": 0.0,
            "reasoning_effort": "none",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(image_png).decode()
                            },
                        },
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    return chat
