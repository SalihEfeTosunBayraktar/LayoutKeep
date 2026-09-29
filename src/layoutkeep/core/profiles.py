"""Setting profiles: one choice that moves several tunables together.

WHY THIS EXISTS: the settings dialog exposes thirty values, and the honest answer to "which ones
should I change for a quick draft?" is a set of four or five that only make sense together.
Offering them as a profile is not a shortcut around the settings - it is the difference between a
user changing the right five and changing none because the list is long.

WHAT A PROFILE IS: a named set of tunable values, applied through the same `tunables.set_value`
path the dialog uses, so nothing bypasses validation and every change is visible (and reversible)
in the settings afterwards. Choosing a profile is a starting point, not a mode: edit any value
afterwards and the profile simply no longer matches.

The two profiles are measured, not marketed:

- `draft` - a first pass to read, not to publish. Parallel requests are pushed to seven (the
  machine here runs LM Studio with seven slots), the readability floor drops to 0.80 so more text
  fits without a flag, and shorter-rendering requests are switched off - each one is a whole extra
  model round-trip. Expect smaller type in tight boxes.
- `quality` - a pass to keep. Parallelism drops back to two (a shared context window costs each
  request tokens), and both the readability floor and the heavy-shrink threshold return to their
  measured defaults (0.85 and 0.95).
"""

from __future__ import annotations

from layoutkeep.core import tunables

#: Values chosen for speed, accepting smaller type instead of extra model round-trips.
_DRAFT = {
    "translation.workers": 7,
    "fit.min_scale": 0.80,
    # Never ask the model for a shorter rendering: that request is a whole extra round-trip per
    # overflowing block, and a draft is about wall-clock time.
    "fit.shorten_below_scale": 0.5,
}

#: Values chosen for the output a reader keeps.
_QUALITY = {
    "translation.workers": 2,
    "fit.min_scale": 0.85,
    # The measured default: a block that only fits because it was shrunk hard is worth one
    # shorter-rendering request (see fit.HEAVY_SHRINK).
    "fit.shorten_below_scale": 0.95,
}

PROFILES: dict[str, dict[str, object]] = {
    "draft": _DRAFT,
    "quality": _QUALITY,
}


def apply(name: str) -> dict[str, object]:
    """Set every value of `name`; returns what was applied. Unknown names are refused loudly.

    Values are written through `tunables.set_value`, so a profile cannot put a setting into a
    state the dialog would reject - and the user sees the result in the dialog, not in a hidden
    state of its own.
    """
    if name not in PROFILES:
        raise ValueError(f"unknown profile {name!r}, expected one of {sorted(PROFILES)}")
    applied: dict[str, object] = {}
    for key, value in PROFILES[name].items():
        tunables.set_value(key, value)
        applied[key] = value
    return applied


def current() -> str | None:
    """Which profile the settings currently match, or None when they match none of them.

    The comparison is exact on purpose: a user who changed one value afterwards has left the
    profile, and saying "draft" anyway would be the kind of small lie this project keeps out of
    its interface.
    """
    for name, values in PROFILES.items():
        if all(tunables.get(key) == value for key, value in values.items()):
            return name
    return None
