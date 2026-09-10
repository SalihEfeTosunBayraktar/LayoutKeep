"""Fitting layer (see docs/CONTRACT.md, D3). Fits translated text into its original box.

Never imports PyMuPDF or any other heavy rendering dependency (D1/D2): real PDF measurement
comes in through a `MeasureFn` callback the PDF writer supplies (see `measure.py`).
"""

from __future__ import annotations

from layoutkeep.fitting.fit import (
    CharBudgetFn,
    FitLayer,
    FitMode,
    FitResult,
    RetranslateFn,
    fit_segment,
    summarize,
)
from layoutkeep.fitting.fontmatch import (
    FontClass,
    FontMatch,
    FontMetrics,
    FontRegistry,
    resolve_font,
)
from layoutkeep.fitting.measure import (
    MeasureFn,
    MeasureResult,
    TextMeasurer,
    make_measure_fn,
    rotated_block_fits,
    rotated_run_length,
)

__all__ = [
    "CharBudgetFn",
    "FitLayer",
    "FitMode",
    "FitResult",
    "FontClass",
    "FontMatch",
    "FontMetrics",
    "FontRegistry",
    "MeasureFn",
    "MeasureResult",
    "RetranslateFn",
    "TextMeasurer",
    "fit_segment",
    "make_measure_fn",
    "resolve_font",
    "rotated_block_fits",
    "rotated_run_length",
    "summarize",
]
