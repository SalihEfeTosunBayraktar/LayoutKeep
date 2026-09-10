"""Text measurement for the fitting layer.

`fitting/` never imports PyMuPDF (docs/CONTRACT.md D1/D2). PyMuPDF's `insert_htmlbox()` already
does exactly what fit.py's layers 1+2 need in a single call: it lays the text out, tells you
whether it fit, and - given `scale_low` - how much it had to shrink the font size to make it fit
(or that even `scale_low` wasn't enough, signalled by `spare_height == -1`). Re-implementing that
line-breaking/shrinking loop inside `fitting/` would duplicate a correct, already-available engine
and would need PyMuPDF anyway, so we don't: `MeasureFn` is a callback the PDF writer supplies -
concretely `layoutkeep.writers.pdf_writer.measure_fit(text, style, bbox, scale_low=..., rotation=...) ->
(fits, scale)` - and `fit.py` calls through it rather than importing pymupdf. `rotation` (see
`MeasureFn` below and `rotated_run_length`/`rotated_block_fits`) is how a rotated block's honest,
smaller-than-the-bbox available room reaches whichever engine is behind the callback.

What `fitting/` still needs of its own, and cannot get through that callback, is a plain
font-metric measurement that doesn't require rendering into a PDF at all: `TextMeasurer` below,
built on fontTools (name/cmap/hmtx tables), used by tests (known text + known font -> expected
line count, with no PDF or PyMuPDF in the loop) and to compute a character budget for layer 3's
re-translation request. It measures real glyph advance widths - it does not estimate width from
character counts. Kerning and complex-script shaping (HarfBuzz) are not applied: phase 1 is
Latin-only (CONTRACT.md), and for non-ligature Latin text, summed glyph advances match real
layout; skipping kerning only makes `wrap_lines` slightly more conservative (it wraps a little
earlier than real rendering would), which is a safe direction to be wrong in for a fitting check.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from layoutkeep.core.docir import BBox, Style

#: (text, style, bbox, scale_low, rotation) -> (fits, scale). Matches `pdf_writer.measure_fit`:
#: `scale_low` there is keyword-only, so callers must call `measure(text, style, bbox,
#: scale_low=min_scale, rotation=...)`, not positionally. `rotation` is `Block.rotation` in
#: degrees counter-clockwise, defaulting to 0.0 for ordinary horizontal text (core/docir.py) -
#: `fit_segment` always passes it as a keyword, so any `measure` implementation must accept it
#: (a non-rotated writer can just ignore the value). `scale` is the fraction of `style.size`
#: actually used (1.0 = full size); `fits` is False when even `scale_low` wasn't enough to fit.
MeasureFn = Callable[..., "tuple[bool, float]"]


# --------------------------------------------------------------------------------------
# Rotated-text geometry
#
# `bbox` is always axis-aligned (core/docir.py, Block.rotation docstring), so for a rotated
# block it is strictly bigger than what the rotated text can actually use - at 45 degrees the
# box's diagonal reaches further than either side, but the text itself only travels in a
# straight line, and that line must stay inside the box from edge to edge. These two functions
# are the "honest measure" described in the fitting brief: the geometry lives here, once, so no
# caller has to re-derive it.
# --------------------------------------------------------------------------------------


def rotated_run_length(bbox: BBox, rotation: float, depth: float) -> float:
    """The longest a `depth`-tall strip of text can run along a baseline rotated `rotation`
    degrees (counter-clockwise, matching `Block.rotation`) before it leaves the axis-aligned
    `bbox`.

    A line of length L and thickness `depth`, rotated by angle theta, has an axis-aligned
    bounding box of
        W = L*|cos theta| + depth*|sin theta|
        H = L*|sin theta| + depth*|cos theta|
    (standard rotated-rectangle AABB). We know W and H (`bbox`) and `depth` (one line's
    height); solving each equation for L gives the longest run that keeps that axis from
    overflowing, and the true limit is whichever axis binds first - the smaller of the two.

    At rotation == 0, cos == 1 and sin == 0, so only the width equation applies and this
    reduces to plain `bbox.width` - unchanged behaviour for ordinary horizontal text. At
    rotation == 90, it is the reverse: only `bbox.height` applies, because a vertical line only
    has the box's height to run along, not its width.
    """
    theta = math.radians(rotation)
    cos_t, sin_t = abs(math.cos(theta)), abs(math.sin(theta))
    limits: list[float] = []
    if cos_t > 1e-9:
        limits.append((bbox.width - depth * sin_t) / cos_t)
    if sin_t > 1e-9:
        limits.append((bbox.height - depth * cos_t) / sin_t)
    if not limits:
        return 0.0
    return max(0.0, min(limits))


def rotated_block_fits(bbox: BBox, rotation: float, length: float, depth: float) -> bool:
    """Whether a `length` x `depth` block of text, baselined at `rotation` degrees, stays
    inside the axis-aligned `bbox` - the forward half of the same geometry `rotated_run_length`
    inverts: the AABB of the rotated block must not exceed `bbox` on either axis.

    `rotated_run_length` only bounds a single line (its `depth` is one line's height); once
    wrapping is done, the whole block (all lines stacked, hence the larger `depth` here) has to
    be re-checked against `bbox` the direct way, because a run that was short enough for one
    line's depth can still overflow once several lines are stacked into it.
    """
    theta = math.radians(rotation)
    cos_t, sin_t = abs(math.cos(theta)), abs(math.sin(theta))
    needed_w = length * cos_t + depth * sin_t
    needed_h = length * sin_t + depth * cos_t
    return needed_w <= bbox.width + 1e-6 and needed_h <= bbox.height + 1e-6


@dataclass(slots=True)
class MeasureResult:
    """Fit/scale/line-count from `TextMeasurer.fits()`. Not part of the `MeasureFn` contract
    (the real callback only returns `(fits, scale)`) - this is the richer, fontTools-only
    reference measurement used by synthetic tests."""

    fits: bool
    scale: float
    lines: int


def _open_ttfont(source: str | bytes | Path, font_number: int = 0) -> TTFont:
    if isinstance(source, bytes):
        return TTFont(io.BytesIO(source), fontNumber=font_number, lazy=True)
    path = str(source)
    if path.lower().endswith(".ttc"):
        return TTCollection(path, lazy=True).fonts[font_number]
    return TTFont(path, fontNumber=font_number, lazy=True)


class TextMeasurer:
    """Real glyph-width text measurement and line-wrapping for one font, via fontTools.

    Used for synthetic fit tests and for computing layer 3's character budget - never for
    driving the actual PDF layout, which stays behind `MeasureFn`.
    """

    def __init__(self, font_source: str | bytes | Path, font_number: int = 0):
        font = _open_ttfont(font_source, font_number)
        self._units_per_em: int = font["head"].unitsPerEm
        self._cmap: dict[int, str] = font.getBestCmap() or {}
        self._hmtx = font["hmtx"]

    def char_width(self, ch: str, size: float) -> float:
        gname = self._cmap.get(ord(ch))
        if gname is None:
            return 0.0
        advance = self._hmtx[gname][0]
        return advance / self._units_per_em * size

    def text_width(self, text: str, size: float) -> float:
        return sum(self.char_width(c, size) for c in text)

    def wrap_lines(self, text: str, size: float, max_width: float) -> list[str]:
        """Greedy word-wrap using real glyph widths. Existing newlines start a new line."""
        lines: list[str] = []
        for paragraph in text.split("\n"):
            words = paragraph.split(" ")
            current = ""
            for word in words:
                candidate = f"{current} {word}" if current else word
                if current and self.text_width(candidate, size) > max_width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        return lines

    @staticmethod
    def block_height(num_lines: int, size: float, line_height: float | None = None) -> float:
        lh = line_height if line_height is not None else size * 1.2
        return num_lines * lh

    def fits(
        self, text: str, style: Style, bbox: BBox, scale: float = 1.0, rotation: float = 0.0
    ) -> MeasureResult:
        """Reference measurement used by tests: known text + known font -> line count and fit.

        `rotation` is degrees CCW (`Block.rotation`). At 0 (or any multiple of 180, which looks
        the same to an axis-aligned box) this is exactly the old unrotated path. Otherwise it
        wraps against the honest run length from `rotated_run_length` instead of `bbox.width`,
        then re-checks the whole wrapped block with `rotated_block_fits` rather than the plain
        `height <= bbox.height` comparison - see those functions for the geometry.
        """
        size = style.size * scale
        if rotation % 180 == 0:
            lines = self.wrap_lines(text, size, bbox.width)
            height = self.block_height(len(lines), size, style.line_height)
            return MeasureResult(fits=height <= bbox.height, scale=scale, lines=len(lines))

        line_h = style.line_height if style.line_height is not None else size * 1.2
        wrap_width = rotated_run_length(bbox, rotation, line_h)
        lines = self.wrap_lines(text, size, wrap_width)
        longest = max((self.text_width(ln, size) for ln in lines), default=0.0)
        depth = self.block_height(len(lines), size, style.line_height)
        fits = rotated_block_fits(bbox, rotation, longest, depth)
        return MeasureResult(fits=fits, scale=scale, lines=len(lines))

    def avg_advance(self, size: float) -> float:
        letters = "abcdefghijklmnopqrstuvwxyz"
        widths = [self.char_width(c, size) for c in letters if ord(c) in self._cmap]
        return sum(widths) / len(widths) if widths else 0.0

    def char_budget(self, style: Style, bbox: BBox, scale: float = 1.0) -> int:
        """How many characters this box can plausibly hold at `scale` - a target for a shorter
        re-translation (layer 3). Derived from the font's own average advance width, not from
        counting characters in a specific string."""
        size = style.size * scale
        lh = style.line_height if style.line_height is not None else size * 1.2
        max_lines = max(1, int(bbox.height // lh))
        avg_w = self.avg_advance(size)
        if avg_w <= 0:
            return 0
        chars_per_line = max(1, int(bbox.width // avg_w))
        return max_lines * chars_per_line


def make_measure_fn(measurer: TextMeasurer, *, steps: int = 16) -> MeasureFn:
    """Build a real, PyMuPDF-free `MeasureFn` from a `TextMeasurer`, for tests and CLI-side
    statistics that need the actual three-layer strategy without a PDF in the loop.

    Shrinks in `steps` even increments from 1.0 down to `scale_low`, stopping at the first scale
    that fits - the same "does it fit, and if not how much smaller" question `insert_htmlbox`
    answers in one call.
    """

    def measure(
        text: str, style: Style, bbox: BBox, scale_low: float = 0.85, rotation: float = 0.0
    ) -> tuple[bool, float]:
        for i in range(steps + 1):
            scale = 1.0 - (1.0 - scale_low) * i / steps
            result = measurer.fits(text, style, bbox, scale, rotation=rotation)
            if result.fits:
                return True, scale
        return False, scale_low

    return measure
