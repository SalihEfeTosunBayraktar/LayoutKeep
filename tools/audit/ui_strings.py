"""Every interface string the code asks for must exist in every language.

`UIStrings.get` falls back to English and then to the key itself, so a key nobody defined shows up
as `MODEL_SEARCH_PLACEHOLDER` in the middle of a settings dialog - which is exactly what happened,
found by the user, not by a test. This walks the source for `UIStrings.NAME` and checks each name
against the translation tables.

The second pass finds Turkish-only literals that are shown to the user but do not go through the
language layer: settings labels/help/warnings, review reasons, status text, dialogs and message
boxes. Internal keys (e.g. `box_crushed`) are fine, but any human-readable Turkish text that reaches
the UI is reported here.

    .venv/Scripts/python tools/audit/ui_strings.py            # report
    .venv/Scripts/python tools/audit/ui_strings.py --quiet    # exit code only (for tests)

Exit code 1 when a language is missing a key, when a key is defined for one language and not
another, or when a user-visible Turkish literal bypasses the translation layer.
"""

from __future__ import annotations

import ast
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

#: Files that are themselves translation tables or contain internal data/heuristics where a
#: Turkish word is expected even in an English build. These are excluded from the literal audit.
_IGNORED_PATHS = {
    "layoutkeep/ui/strings.py",
    "layoutkeep/ui/welcome_text.py",
    "layoutkeep/ui/help_text.py",
    "layoutkeep/ui/languages.py",
    "layoutkeep/core/copies.py",
    "layoutkeep/core/terms.py",
    "layoutkeep/core/protect.py",
    "layoutkeep/core/langs.py",
    "layoutkeep/core/capabilities.py",
    "layoutkeep/core/reference.py",
    "layoutkeep/core/keywords.py",
    "layoutkeep/core/range_helper.py",
    "layoutkeep/fitting/fontmatch.py",
    "layoutkeep/providers/_http_compat.py",
    "layoutkeep/providers/memory.py",
    "layoutkeep/providers/fake.py",
    "layoutkeep/providers/cached.py",
    "layoutkeep/providers/base.py",
    "layoutkeep/providers/_nonprose.py",
    "layoutkeep/writers/converter.py",
    "layoutkeep/writers/epub_generator.py",
    "layoutkeep/writers/docx_generator.py",
    "layoutkeep/writers/html_writer.py",
    "layoutkeep/writers/pdf_generator.py",
    "layoutkeep/assets/__init__.py",
}

#: Docstring text is allowed to be bilingual because it is for developers, not users.
_DOCSTRING_PARENTS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _has_turkish(s: str) -> bool:
    return bool(re.search(r"[çğışöüÇĞİŞÖÜ]", s))


def used_keys() -> dict[str, set[str]]:
    """Every `UIStrings.NAME` the source mentions, with the files that mention it."""
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _USAGE.finditer(text):
            found.setdefault(match.group(1), set()).add(str(path.relative_to(SRC)))
    return found


def _is_docstring_node(tree: ast.AST, node: ast.Constant) -> bool:
    """A constant that is the first statement in a module/class/function body is a docstring."""
    for parent in ast.walk(tree):
        if isinstance(parent, _DOCSTRING_PARENTS):
            body = getattr(parent, "body", [])
            if body and isinstance(body[0], ast.Expr) and body[0].value is node:
                return True
            # Also handle ast.Constant directly assigned as docstring in newer Python
            if body and body[0] is node:
                return True
    return False


def turkish_literals() -> list[tuple[str, int, str]]:
    """User-visible Turkish strings that bypass UIStrings, grouped by file:line."""
    found: list[tuple[str, int, str]] = []
    for path in SRC.rglob("*.py"):
        rel = "layoutkeep/" + "/".join(path.relative_to(SRC / "layoutkeep").parts)
        if rel in _IGNORED_PATHS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        docstring_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, _DOCSTRING_PARENTS) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr):
                    first = first.value
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    for offset, _ in enumerate(first.value.splitlines()):
                        docstring_lines.add(first.lineno + offset)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            s = node.value
            if ";;" in s:
                # File filters contain Turkish but are not user-readable sentences.
                continue
            if not _has_turkish(s):
                continue
            if node.lineno in docstring_lines:
                continue
            found.append((rel, node.lineno, s.replace("\\n", " ").replace("\n", " ")[:120]))
    return sorted(found)


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

    literals = turkish_literals()
    if literals:
        problems += len(literals)
        if not quiet:
            print(f"=== Kullaniciya giden ama ceviriden gecmeyen Turkce metinler ({len(literals)}):")
            for rel, line, s in literals:
                print(f"   {rel}:{line}  {s}")
            print()

    if not quiet:
        print(f"diller: {{ {', '.join(f'{k}: {len(v)}' for k, v in sorted(languages.items()))} }} · "
              f"kodda kullanilan: {len(used)} · gecmeyen: {len(literals)}")
        print("SONUC:", "temiz ✓" if problems == 0 else f"{problems} eksik ✗")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
