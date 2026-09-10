"""Enforces contract D2: the provider layer knows nothing about layout.

None of bbox, Style, Page, fitz, pymupdf may appear anywhere under src/layoutkeep/providers/.
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_NAMES = ("bbox", "Style", "Page", "fitz", "pymupdf")

PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "src" / "layoutkeep" / "providers"


def test_providers_source_never_mentions_layout_concepts():
    py_files = sorted(PROVIDERS_DIR.rglob("*.py"))
    assert py_files, "expected .py files under src/layoutkeep/providers/"

    violations: list[str] = []
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN_NAMES:
            if name in text:
                violations.append(f"{path.relative_to(PROVIDERS_DIR)}: contains {name!r}")

    assert not violations, "layout-blindness (D2) violated:\n" + "\n".join(violations)
