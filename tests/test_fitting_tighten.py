"""The fitting ladder gains a leading step: tighten the lines before asking the model.

Why this step exists, measured: on the book's first twelve finished chunks, 352 of 6,570 blocks
ended as "the translation did not fit, shrinking was not enough" - the largest single review-flag
class, six times the next one. A translation that overflows by a line usually fits once its lines
sit closer together, and tightening costs no model round-trip and no shrink.

The order matters and is asserted here: the step runs *before* the shorter-rendering request,
because a model call is the expensive answer and this one is free. It is also a real change to the
page (tighter leading), so it is a `FitLayer` of its own and the result carries the leading the
caller must write into the block's spans - the writer already honours `style.line_height` in its
CSS (see tests/test_writers_line_height.py).
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Style
from layoutkeep.core.docir import Segment
from layoutkeep.fitting.fit import FitLayer, FitMode, fit_segment
from layoutkeep.fitting.measure import TextMeasurer, make_measure_fn


def _measure():
    from pathlib import Path

    font = Path(__file__).resolve().parents[1] / "src/layoutkeep/assets/fonts/Carlito-Regular.ttf"
    return make_measure_fn(TextMeasurer(font))


def _segment(text: str) -> Segment:
    return Segment(source=text, target=text, block_id="b1")


#: A box that fits the text at a tighter leading but not at the engine's own.
_TEXT = ("the quick brown fox jumps over the lazy dog and keeps going for a while " * 3).strip()


def test_a_translation_that_only_fits_with_tighter_lines_is_tightened() -> None:
    measure = _measure()
    style = Style(font_family="Carlito", size=11.0)
    # Room for six lines at 11pt leading, not at the engine's own (which the measurer takes as
    # `line_height or size * 1.2`).
    box = BBox(0, 0, 220, 62)

    result = fit_segment(_segment(_TEXT), style, box, measure, mode=FitMode.STRICT)

    assert result.layer is FitLayer.TIGHTENED, result
    assert result.line_height is not None and result.line_height < style.size * 1.2
    assert not result.needs_review, "a tightened fit is a fit, not a flag"
    assert result.text == _TEXT, "tightening changes the leading, never the words"


def test_tightening_is_tried_before_asking_the_model() -> None:
    """The cheaper answer wins: the model is asked only when even the tightest leading fails."""
    measure = _measure()
    style = Style(font_family="Carlito", size=11.0)
    box = BBox(0, 0, 220, 62)
    asked: list[int] = []

    def retranslate(_segment, budget: int) -> str:
        asked.append(budget)
        return "kısa"

    result = fit_segment(
        _segment(_TEXT), style, box, measure, mode=FitMode.STRICT, retranslate=retranslate
    )

    assert result.layer is FitLayer.TIGHTENED
    assert asked == [], "the model was asked for a shorter text that tightening made unnecessary"


def test_text_that_fits_as_is_is_not_tightened() -> None:
    """The step must not fire when there is nothing to rescue - every block in every document
    would come out with tighter leading."""
    measure = _measure()
    style = Style(font_family="Carlito", size=11.0)
    box = BBox(0, 0, 600, 400)

    result = fit_segment(_segment("short text"), style, box, measure, mode=FitMode.STRICT)

    assert result.layer is FitLayer.AS_IS
    assert result.line_height is None


def test_text_that_fits_at_no_leading_still_overflows_and_flags() -> None:
    """The honest end of the ladder is unchanged: if nothing fits, the block is flagged rather
    than silently drawn smaller."""
    measure = _measure()
    style = Style(font_family="Carlito", size=11.0)
    box = BBox(0, 0, 120, 30)

    result = fit_segment(_segment(_TEXT), style, box, measure, mode=FitMode.STRICT)

    assert result.layer is FitLayer.OVERFLOW
    assert result.needs_review


def test_an_explicit_line_height_on_the_style_is_respected() -> None:
    """A block whose style already names a leading must not be tightened further on top of it."""
    measure = _measure()
    style = Style(font_family="Carlito", size=11.0, line_height=13.2)
    box = BBox(0, 0, 600, 400)

    result = fit_segment(_segment("short text"), style, box, measure, mode=FitMode.STRICT)

    assert result.line_height is None, "the block's own leading is the caller's business"
