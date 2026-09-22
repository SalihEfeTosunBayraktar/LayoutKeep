"""Small builders the setup screen uses, split out of its UI builder class.

`fill_format_combo` is the one with a story: a target this build cannot do well is listed, marked
with a lock and the one sentence that says what it would cost, and cannot be picked.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QComboBox

from layoutkeep.core import capabilities
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

__all__ = ["fill_format_combo"]


def fill_format_combo(combo: QComboBox, source_path: str) -> None:
    """(Re)fill the format box, keeping whatever was chosen.

    A target this build cannot do well is listed, marked with a lock and the one sentence
    that says what it would cost, and cannot be picked. Leaving it out would say the project
    does not convert to EPUB; leaving it selectable would say it does it well. Neither is
    true - see `core/capabilities.py` and docs/ENGINE-ARCHITECTURE.md.
    """
    # Imported lazily: job_setup.py imports this module, so a top-level import would cycle.
    from layoutkeep.ui.job_setup import _format_choices

    chosen = combo.currentData()
    source_suffix = Path(source_path).suffix.lower()
    locked_colour = ThemeManager.current_palette().text_muted

    combo.blockSignals(True)
    combo.clear()
    model = combo.model()
    for row, (ext, label) in enumerate(_format_choices()):
        unlocked = bool(source_suffix) and capabilities.is_open(source_suffix, ext)
        text = label if unlocked else f"{label} — {UIStrings.get('LOCKED_SUFFIX')}"
        combo.addItem(text, ext)
        if unlocked:
            continue
        item = model.item(row)
        item.setEnabled(False)
        item.setIcon(get_svg_icon("lock", color=locked_colour, size=14))
        reason_key = capabilities.lock_reason_key(capabilities.resolve_target(source_suffix, ext))
        if reason_key:
            item.setToolTip(UIStrings.get(reason_key))

    index = combo.findData(chosen) if chosen is not None else -1
    if index < 0 or not model.item(index).isEnabled():
        index = next(
            (row for row in range(combo.count()) if model.item(row).isEnabled()),
            0,
        )
    combo.setCurrentIndex(index)
    combo.blockSignals(False)
