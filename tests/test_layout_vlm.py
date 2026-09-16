"""The vision classifier answers the question the heuristics could not, and fails quietly.

Every rule that tried to tell a heading from a formula from a running header worked off the
height of the detected box, and each was calibrated on one page and broke another. Measured on
page 54 of `computer-systems-Architecture.pdf`, our heuristics called three displayed equations
"heading" and redrew them at 9.00pt instead of ~6.3pt, and gave the running header 9.57pt
because a large folio shared its line. Shown the page with its regions numbered, the model
labelled the folio `page_number`, the header `running_header`, and all three equations
`formula`.

These tests cover the parts that have to hold regardless of which model is behind it: that a
real reply is read, that a broken one costs nothing, and that an unknown label is dropped rather
than guessed at.
"""

from __future__ import annotations

from PIL import Image

from layoutkeep.core.docir import BlockRole
from layoutkeep.ocr.layout_vlm import RENDER_WIDTH, classify, parse

_REAL_REPLY = """```json
[
  {"n": 1, "label": "page_number", "size": "same"},
  {"n": 2, "label": "running_header", "size": "smaller"},
  {"n": 6, "label": "formula", "size": "smaller"},
  {"n": 9, "label": "body", "size": "same"}
]
```"""


def _page() -> Image.Image:
    return Image.new("RGB", (1325, 1767), "white")


def _boxes(n: int) -> list[tuple[float, float, float, float]]:
    return [(20.0, 10.0 + i * 20, 400.0, 26.0 + i * 20) for i in range(n)]


def test_a_real_reply_is_read() -> None:
    """Verbatim from the model, fence and all."""
    verdicts = parse(_REAL_REPLY)
    assert verdicts[1].role is BlockRole.PAGE_NUMBER
    assert verdicts[2].role is BlockRole.HEADER
    assert verdicts[6].role is BlockRole.FORMULA
    assert verdicts[9].role is BlockRole.BODY
    assert verdicts[2].size == "smaller"


def test_an_unknown_label_is_dropped_not_guessed() -> None:
    """A wrong role is worse than no role - the caller keeps its own answer for that region."""
    verdicts = parse('[{"n":1,"label":"marginalia","size":"same"},{"n":2,"label":"body"}]')
    assert 1 not in verdicts
    assert verdicts[2].role is BlockRole.BODY
    assert verdicts[2].size == "same", "a missing size must not become an invalid one"


def test_prose_instead_of_json_costs_nothing() -> None:
    assert parse("I'm afraid I can't help with that.") == {}
    assert parse("[not json at all]") == {}


def test_a_server_that_is_not_there_costs_nothing() -> None:
    """The classifier is an improvement, not a dependency: a page read slightly wrong beats a
    page not read."""

    def dead(prompt: str, image_png: bytes) -> str:
        raise OSError("connection refused")

    assert classify(_page(), _boxes(3), ["a", "b", "c"], dead) == {}


def test_no_regions_makes_no_request() -> None:
    def explode(prompt: str, image_png: bytes) -> str:
        raise AssertionError("should not have been called")

    assert classify(_page(), [], [], explode) == {}


def test_the_page_is_sent_annotated_and_downscaled() -> None:
    """What the model is shown has to carry the numbers it is asked about, and be small enough
    to send: the source scan is 1325px wide here and 600 DPI in the real book."""
    seen: dict[str, object] = {}

    def capture(prompt: str, image_png: bytes) -> str:
        seen["prompt"] = prompt
        seen["png"] = image_png
        return _REAL_REPLY

    classify(_page(), _boxes(4), ["first", "second", "third", "fourth"], capture)

    import io

    sent = Image.open(io.BytesIO(seen["png"]))  # type: ignore[arg-type]
    assert sent.width == RENDER_WIDTH, sent.size
    assert sent.convert("RGB").getcolors(maxcolors=1 << 16) is not None
    # The boxes were drawn: a blank page would be a single colour.
    assert len(sent.convert("RGB").getcolors(maxcolors=1 << 16) or []) > 1
    assert "1: 'first'" in str(seen["prompt"])
    assert "regions 1 to 4" in str(seen["prompt"])
