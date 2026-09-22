"""Every interface string must exist in every language.

The gap was found by the user, not by a test: a settings dialog showed the raw key
`MODEL_SEARCH_PLACEHOLDER`, because `UIStrings.get` falls back to English and then to the key
itself, so a key nobody defined renders as its own name. These two tests run the audit that found
it - `tools/audit/ui_strings.py` - and keep the languages in step.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from layoutkeep.ui.strings import _TRANSLATIONS


def test_the_audit_reports_no_missing_key():
    """The audit is the source of truth: it reads the class, not the fallback."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audit" / "ui_strings.py"), "--quiet"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        "cevrilmemis anahtar var:\n"
        + subprocess.run(
            [sys.executable, str(ROOT / "tools" / "audit" / "ui_strings.py")],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        ).stdout
    )


def test_the_languages_hold_the_same_keys():
    tables = {lang: set(table) for lang, table in _TRANSLATIONS.items()}
    names = sorted(tables)
    assert len(names) >= 2, "en az iki dil olmali"
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            only_first = sorted(tables[first] - tables[second])
            only_second = sorted(tables[second] - tables[first])
            assert tables[first] == tables[second], (
                f"{first} ile {second} ayni anahtarlari tutmuyor: "
                f"yalniz {first}={only_first[:8]}, yalniz {second}={only_second[:8]}"
            )
