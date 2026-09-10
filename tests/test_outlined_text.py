"""Measures ocr.outlined_text.find_outlined_text against synthetic fixtures: does it catch a
word missing from the text layer, and does it stay quiet on a page whose text layer is complete?
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fixtures.build_outlined_fixture import (
    BODY_TEXT,
    FULLY_COVERED_TEXT,
    OUTLINED_WORD,
    build_fully_covered_page,
    build_mixed_page,
)

from layoutkeep.ocr.outlined_text import find_outlined_text


def test_finds_word_missing_from_text_layer(tmp_path: Path) -> None:
    src = tmp_path / "mixed.png"
    build_mixed_page(src)
    # The fake text layer reports the body text but not OUTLINED - the mixed-page scenario:
    # a real text layer alongside one word that only exists as drawn/outlined text.
    extracted_text = BODY_TEXT

    missing = find_outlined_text(src, extracted_text)

    assert len(missing) == 1
    assert missing[0].text.strip() == OUTLINED_WORD


def test_no_false_positives_on_fully_covered_page(tmp_path: Path) -> None:
    src = tmp_path / "covered.png"
    build_fully_covered_page(src)
    extracted_text = FULLY_COVERED_TEXT

    missing = find_outlined_text(src, extracted_text)

    assert missing == []


def test_low_confidence_reads_are_not_reported(tmp_path: Path) -> None:
    src = tmp_path / "mixed.png"
    build_mixed_page(src)

    # An unreasonably high confidence floor should suppress every read, including the genuinely
    # missing word - low-confidence OCR is not trustworthy evidence of anything.
    missing = find_outlined_text(src, BODY_TEXT, min_confidence=1.01)

    assert missing == []
