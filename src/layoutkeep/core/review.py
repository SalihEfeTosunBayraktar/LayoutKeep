"""Review flags a front-end can explain better than "it did not fit".

WHY THIS EXISTS: the fitting engine knows *why* a block was flagged and the front-ends did not ask.
Measured on the book: most flags are not a translation that could not be shortened, they are boxes
`room_below` crushed to six points to keep clear of the next block - and nothing fits in six
points. Telling a user "shrinking was not enough" then sends them to the wrong knob.

The engine reports a machine *key* (`FitResult.review_reason`); each front-end stores the
UIStrings key `storage_key` maps it to, so a project file reads the same whether the desktop
runner or the CLI wrote it. Text reaches the user only at display time, through
`ui.strings.format_review_reason` - the same split `ui.progress.format_phase` uses for phase
names. This module stays pure keys on purpose: core must not import the UI layer.
"""

from __future__ import annotations

#: The key the fitting pass sets when a block's measured box was shortened to its floor.
BOX_CRUSHED = "box_crushed"

#: Machine keys that mean "the box, not the text", mapped to the UIStrings key both front-ends
#: store. Anything unmapped is left to the front-end's generic line (`REVIEW_FIT_FAILED`).
_STORAGE_KEYS = {
    BOX_CRUSHED: "REVIEW_BOX_CRUSHED",
}


def storage_key(machine_key: str) -> str:
    """The UIStrings key a front-end stores for an engine key, or "" for one we do not know.

    Empty rather than a guess: the caller falls back to its own generic reason, which reads
    better than a machine name leaking into a project file.
    """
    return _STORAGE_KEYS.get(machine_key, "")
