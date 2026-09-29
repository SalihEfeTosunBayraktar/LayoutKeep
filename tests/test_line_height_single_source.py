"""How tall a rendered line is has to be one number, not three copies of it.

The reader derives a scanned block's font size so that size x line-height reproduces the pitch
it measured off the page, and grants blank paper below a block in units of that same line
height. The writer then stacks the lines at size x line-height. If those two disagree, every
scanned page comes out mis-sized - and nothing was stopping them: 1.2 was declared separately in
`readers/image_reader.py`, in `writers/pdf_writer.py`, and a third time as the
`merge.line_height_ratio` tunable, with no import or test tying them together. The reader's own
docstring said it "must be the one number, not two that drift apart", which is a comment, not a
guarantee.

They cannot import each other - readers and writers must not know about each other (CONTRACT.md
D1) - so the one number lives where both may read it: the tunable, which has the added merit of
being adjustable without a code edit.

Read at use, never captured at import. A module-level constant computed from a tunable is
evaluated once when the module loads, so a setting changed afterwards would never be seen -
`fitting/fit.py` carries the same warning about default arguments for the same reason.
"""

from __future__ import annotations

import pytest

from layoutkeep.core import tunables
from layoutkeep.readers.image_reader import box_height_to_font_size, line_height_ratio
from layoutkeep.writers.pdf_writer import writer_line_height_ratio

_KEY = "merge.line_height_ratio"


def test_reader_and_writer_read_the_same_number() -> None:
    """The drift this exists to prevent."""
    assert line_height_ratio() == writer_line_height_ratio()


def test_both_follow_the_tunable() -> None:
    assert line_height_ratio() == tunables.get(_KEY)
    assert writer_line_height_ratio() == tunables.get(_KEY)


def test_the_derived_font_size_factor_follows_it_too() -> None:
    """`box_height_to_font_size` turns a detector's box height into a type size, and it only
    holds while the line height it assumes is the one the writer uses."""
    ratio = line_height_ratio()
    assert box_height_to_font_size() * ratio == pytest.approx(0.957)


def test_a_changed_setting_is_seen_without_a_reimport() -> None:
    """Captured at import, a tunable is not a tunable."""
    original = tunables.get(_KEY)
    try:
        tunables.set_value(_KEY, 1.5)
        assert line_height_ratio() == 1.5
        assert writer_line_height_ratio() == 1.5
        assert box_height_to_font_size() * 1.5 == pytest.approx(0.957)
    finally:
        tunables.set_value(_KEY, original)
    assert line_height_ratio() == original
