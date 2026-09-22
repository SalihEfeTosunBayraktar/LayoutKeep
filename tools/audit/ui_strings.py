"""Every interface string the code asks for must exist in every language.

`UIStrings.get` falls back to English and then to the key itself, so a key nobody defined shows up
as `MODEL_SEARCH_PLACEHOLDER` in the middle of a settings dialog - which is exactly what happened,
found by the user, not by a test. This walks the source for `UIStrings.NAME` and checks each name
against the translation tables.

    .venv/Scripts/python tools/audit/ui_strings.py            # report
    .venv/Scripts/python tools/audit/ui_strings.py --quiet    # exit code only (for tests)

Exit code 1 when a language is missing a key, or when a key is defined for one language and not
another.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from layoutkeep.ui.strings import UIStrings, _TRANSLATIONS  # noqa: E402

_USAGE = re.compile(r"UIStrings\.([A-Z][A-Z0-9_]+)")

#: Names on the class that are not interface text: `SUPPORTED_LANGUAGES` is a tuple of language
#: codes and labels. The audit reads the class, not the resolution, so a missing key cannot hide
#: behind the metaclass's fallback.
_NON_TEXT = {name for name, value in vars(UIStrings).items() if not isinstance(value, str)}


def used_keys() -> dict[str, set[str]]:
    """Every `UIStrings.NAME` the source mentions, with the files that mention it."""
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _USAGE.finditer(text):
            found.setdefault(match.group(1), set()).add(str(path.relative_to(SRC)))
    return found


def main() -> int:
    quiet = "--quiet" in sys.argv
    languages = {name: set(table) for name, table in _TRANSLATIONS.items()}
    used = {key: files for key, files in used_keys().items() if key not in _NON_TEXT}
    problems = 0

    for language, table in sorted(languages.items()):
        missing = sorted(key for key in used if key not in table)
        if missing:
            problems += len(missing)
            if not quiet:
                print(f"=== {language}: kodda kullanilan ama sozlukte OLMAYAN ({len(missing)}):")
                for key in missing:
                    files = ", ".join(sorted(used[key])[:3])
                    print(f"   {key:44s} <- {files}")
                print()

    names = sorted(languages)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            only_first = sorted(languages[first] - languages[second])
            only_second = sorted(languages[second] - languages[first])
            if only_first or only_second:
                problems += len(only_first) + len(only_second)
                if not quiet:
                    print(f"=== {first} ile {second} arasindaki fark:")
                    if only_first:
                        print(f"   yalniz {first} ({len(only_first)}): {only_first[:12]}")
                    if only_second:
                        print(f"   yalniz {second} ({len(only_second)}): {only_second[:12]}")
                    print()

    if not quiet:
        print(f"diller: { {k: len(v) for k, v in languages.items()} } · kodda kullanilan: {len(used)}")
        print("SONUC:", "temiz ✓" if problems == 0 else f"{problems} eksik ✗")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
