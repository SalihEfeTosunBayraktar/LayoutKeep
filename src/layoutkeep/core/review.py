"""Review flags a front-end can explain better than "it did not fit".

WHY THIS EXISTS: the fitting engine knows *why* a block was flagged and the front-ends did not ask.
Measured on the book: most flags are not a translation that could not be shortened, they are boxes
`room_below` crushed to six points to keep clear of the next block - and nothing fits in six
points. Telling a user "shrinking was not enough" then sends them to the wrong knob.

The engine reports a *key* (`FitResult.review_reason`); each front-end turns it into its own
language - the CLI uses `sentence()`, the desktop application uses its `UIStrings` table, the same
split `ui.progress.format_phase` uses for phase names.
"""

from __future__ import annotations

from layoutkeep.ui.strings import UIStrings

#: The key the fitting pass sets when a block's measured box was shortened to its floor.
BOX_CRUSHED = "box_crushed"

#: Keys that mean "the box, not the text". Anything else is left to the front-end's generic line.
_SENTENCES = {
    BOX_CRUSHED: "REVIEW_BOX_CRUSHED",
}


def sentence(key: str) -> str:
    """Return the translated sentence for a machine key, or an empty string if unknown.

    Empty rather than the key itself: a caller that gets nothing falls back to its own wording,
    which reads better than a machine name leaking into a review list.
    """
    return UIStrings.get(_SENTENCES.get(key, "")) if key in _SENTENCES else ""
