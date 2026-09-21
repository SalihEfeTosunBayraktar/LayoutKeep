"""The scan-detection thresholds are tunable - and their defaults are the old constants, exactly.

WHY THIS EXISTS: the thresholds were module constants, so a cover page carrying a few words and a
large picture was classified as a scan and its text never reached translation. They are now developer
settings. The risk of such a change is that the pipeline quietly starts behaving differently for
everyone who never opens the settings, so the defaults are pinned here to the constants they replaced,
and the one behaviour the user actually asked for - making a cover's text translate as text - is
exercised. Both assertions fail if someone edits one side and not the other.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from layoutkeep.core import tunables
from layoutkeep.readers import image_reader, pdf_reader
from layoutkeep.readers.image_reader import is_scanned_page

#: A page the size of the textbook in the corpus, carrying a cover's worth of words.
_COVER_TEXT = "ON THE ORIGIN OF SPECIES"
_COVER_AREA_PT2 = 318.0 * 424.0


def test_the_defaults_are_the_constants_they_replaced() -> None:
    """Nothing moves for anyone who never opens the settings."""
    assert tunables.definition("reader.scan_text_density").default == image_reader._SCANNED_TEXT_DENSITY
    assert tunables.definition("reader.scan_image_coverage").default == image_reader._SCANNED_IMAGE_COVERAGE
    assert (
        tunables.definition("reader.scan_image_coverage_layer").default
        == pdf_reader._SCANNED_IMAGE_COVERAGE_FOR_LAYER
    )


def test_the_reader_reads_the_tunable_not_the_constant() -> None:
    """Unchanged value, different source: the answer is the same either way."""
    assert tunables.get("reader.scan_text_density") == image_reader._SCANNED_TEXT_DENSITY
    assert tunables.get("reader.scan_image_coverage") == image_reader._SCANNED_IMAGE_COVERAGE


def test_a_cover_page_is_a_scan_by_default_and_text_once_the_threshold_drops() -> None:
    """The setting the user asked for: a cover's words can be translated as words."""
    assert is_scanned_page(_COVER_TEXT, _COVER_AREA_PT2, 1.0) is True

    was = tunables.get("reader.scan_text_density")
    tunables.set_value("reader.scan_text_density", 0.0)
    try:
        assert is_scanned_page(_COVER_TEXT, _COVER_AREA_PT2, 1.0) is False
    finally:
        tunables.set_value("reader.scan_text_density", was)

    assert is_scanned_page(_COVER_TEXT, _COVER_AREA_PT2, 1.0) is True


def test_a_page_with_no_picture_is_never_a_scan() -> None:
    """The coverage floor still guards the density answer, tunable or not."""
    assert is_scanned_page("", _COVER_AREA_PT2, 0.0) is False
