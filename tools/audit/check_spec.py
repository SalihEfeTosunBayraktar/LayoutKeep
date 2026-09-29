"""Does the PyInstaller spec see every module the app imports lazily?

PyInstaller's static analysis only follows imports at module top level. This repository defers
heavy imports into function bodies (readers, writers, the PDF pass, provider wiring), so a spec
that misses one builds a perfectly fine exe that dies with `ModuleNotFoundError` the first time
that code path runs - and only then.

What this checks, for each spec in `packaging/`:

1. every first-party module imported inside a function body is reachable, either listed in
   `hiddenimports` or importable by following top-level imports from something that is listed;
2. every `hiddenimports` entry that is a first-party module actually exists (a rename leaves a
   stale name behind, and PyInstaller fails the whole build for it).

Run: python tools/audit/check_spec.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def _module_name(path: Path) -> str:
    relative = path.relative_to(SRC).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(tree: ast.AST, *, lazy_only: bool) -> set[str]:
    """Module-level or function-body imports of first-party modules in one file."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.col_offset > 0 and not lazy_only:
            continue
        if node.col_offset == 0 and lazy_only:
            continue
        for alias in node.names:
            name = alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
            if name.startswith("layoutkeep"):
                found.add(name)
    return found


def _top_level_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "layoutkeep" or node.module.startswith("layoutkeep."):
                found.add(node.module)
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
            else:
                found.update(alias.name for alias in node.names if alias.name.startswith("layoutkeep"))
    return {name for name in found if name.startswith("layoutkeep")}


def _reachable(seeds: set[str], top_level: dict[str, set[str]]) -> set[str]:
    """Everything importable by following top-level imports from `seeds`."""
    seen: set[str] = set()
    queue = list(seeds)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend(top_level.get(name, ()))
        parent = name.rsplit(".", 1)[0]
        queue.extend(top_level.get(parent, ()))
    return seen


def _module_of(name: str, known: set[str]) -> str:
    """The module a dotted name belongs to - `pkg.mod.func` is `pkg.mod`, `pkg.mod` is itself."""
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in known:
            return candidate
        parts.pop()
    return name


def main() -> int:
    top_level = {_module_name(path): _top_level_imports(path) for path in SRC.rglob("*.py")}
    known = set(top_level)
    lazy: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        names = {_module_of(name, known) for name in _imports(tree, lazy_only=True)}
        if names:
            lazy[_module_name(path)] = names

    problems = 0
    for spec in sorted((ROOT / "packaging").glob("*.spec")):
        text = spec.read_text(encoding="utf-8")
        listed = {
            name for name in re.findall(r'"(layoutkeep[\w.]*)"', text) if not name.endswith(".ico")
        }
        seeds = {name for name in listed if name.startswith("layoutkeep")} | {"layoutkeep"}
        reach = _reachable(seeds, top_level)

        missing: dict[str, set[str]] = {}
        for importer, names in sorted(lazy.items()):
            for name in sorted(names):
                if name in reach:
                    continue
                missing.setdefault(name, set()).add(importer)

        print(f"{spec.name}: {len(listed)} hidden imports listed")
        if missing:
            problems += len(missing)
            print(f"  MISSING ({len(missing)}) - the exe would fail on these at runtime:")
            for name, importers in sorted(missing.items()):
                print(f"    {name}   (imported by {', '.join(sorted(importers))})")
        stale = sorted(name for name in listed if name not in known)
        if stale:
            problems += len(stale)
            print(f"  STALE ({len(stale)}) - listed but no such module:")
            for name in stale:
                print(f"    {name}")
        if not missing and not stale:
            print("  every lazy import is reachable, no stale names")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
