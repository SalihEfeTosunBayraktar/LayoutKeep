"""No class outgrows the line budget (SOUL.md: a class body over ~220 lines gets split).

D-017 split TranslationWorker for exactly this reason and nothing pinned the result: the
automatic glossary, the references setting and the glossary check were added back on top and the
class was 274 lines again. A budget nothing measures is a budget that drifts, so this measures it.

The span is the class's own `end_lineno - lineno + 1` from the AST - docstring and blank lines
included, because those are the lines a reader has to get through. The classes this watches are
the ones the split queue has already emptied; the ones still over budget are named in D-017 and
each is a line to delete here, not a reason to loosen the rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The rule's number, from SOUL.md.
BUDGET = 220

#: (path under src, class name) for the classes already brought under the budget.
WATCHED = [
    ("layoutkeep/ui/worker.py", "TranslationWorker"),
    ("layoutkeep/ui/job_setup.py", "_JobSetupUiBuilder"),
]


def _span(relative: str, name: str) -> int:
    tree = ast.parse((ROOT / "src" / relative).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            assert node.end_lineno is not None
            return node.end_lineno - node.lineno + 1
    raise AssertionError(f"{name} is not defined in src/{relative}")


@pytest.mark.parametrize(("relative", "name"), WATCHED)
def test_the_class_body_stays_under_the_line_budget(relative: str, name: str) -> None:
    span = _span(relative, name)
    assert span <= BUDGET, f"{name} is {span} lines, over the {BUDGET}-line budget"
