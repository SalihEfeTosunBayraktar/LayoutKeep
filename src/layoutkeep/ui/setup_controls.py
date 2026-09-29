"""Small builders the setup screen uses, split out of its UI builder class.

`fill_format_combo` is the one with a story: a target this build cannot do well is listed, marked
with a lock and the one sentence that says what it would cost, and cannot be picked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QPushButton

from layoutkeep.core import capabilities
from layoutkeep.ui.icons import get_svg_icon
from layoutkeep.ui.job import ProviderConfig
from layoutkeep.ui.strings import UIStrings
from layoutkeep.ui.theme import ThemeManager

#: Width of the square icon-only buttons on the setup screen (browse, provider settings).
ICON_BUTTON_WIDTH = 42

__all__ = ["ICON_BUTTON_WIDTH", "ProviderControls", "build_provider_controls", "fill_format_combo"]


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


@dataclass
class ProviderControls:
    """The provider-side widgets and state the setup screen needs, built in one place."""

    store: object
    combo: object
    config: object
    provider_btn: QPushButton
    start_btn: QPushButton


def build_provider_controls() -> ProviderControls:
    """Builds the profile store, the profile box, the active config and the two buttons.

    There is deliberately no provider-kind dropdown here. There used to be one, but it was never
    added to a layout - invisible, and yet it decided the kind of every job, which is why DeepL
    could be chosen nowhere even though the provider was finished. The profile now carries the
    kind, and the profile is what the setup screen selects.
    """
    from layoutkeep.ui.provider_combo import ProviderComboBox
    from layoutkeep.ui.provider_profile import ProviderProfileStore

    store = ProviderProfileStore()
    combo = ProviderComboBox()
    active = store.get_profile(store.get_active_profile_name())
    config = active.to_config() if active else ProviderConfig(kind="openai")

    provider_btn = QPushButton()
    provider_btn.setIcon(get_svg_icon("sliders", color=ThemeManager.current_palette().accent, size=18))
    provider_btn.setFixedWidth(ICON_BUTTON_WIDTH)
    provider_btn.setToolTip(UIStrings.PROVIDER_SETTINGS_BTN)
    start_btn = QPushButton(UIStrings.START_TRANSLATION_BTN)
    start_btn.setProperty("class", "primary")
    start_btn.setIcon(get_svg_icon("play", color=ThemeManager.current_palette().accent_text, size=18))
    start_btn.setMinimumHeight(42)
    return ProviderControls(store, combo, config, provider_btn, start_btn)
