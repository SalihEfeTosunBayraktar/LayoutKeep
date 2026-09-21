"""Measure candidate pairs for phase 2 against the RICH fixtures, not the synthetic ones.

format_matrix.py's numbers (pdf->html 101%, epub->html 104%, docx->png 100%, epub->png 101%)
come from tiny synthetic fixtures - exactly the scale the isolating-residual-gaps skill warns
about. This reruns the same identity-translation measurement against the rich fixtures
(tests/fixtures/rich_report.*, rich_book.epub) that already exposed two silent styling losses
in phase 1, before any of these pairs get added to capabilities.OPEN_PAIRS.

    .venv/Scripts/python.exe tools/audit/faz2_candidates.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))

from format_matrix import count_docir, count_output, run_pair  # noqa: E402

CANDIDATES = [
    ("rich_report.pdf", "html"),
    ("rich_report.pdf", "epub"),
    ("rich_book.epub", "html"),
    ("rich_book.epub", "docx"),
    ("rich_book.epub", "png"),
    # Not open, and not to be opened from this measurement alone: the user asked that no pair be
    # described as working on the published pages before they have verified it themselves. The
    # implementation reflows an EPUB to PDF already (tests/test_epub_pdf_reflow.py pins it), so this
    # row exists to hand them the numbers - `capabilities.OPEN_PAIRS` is unchanged.
    ("rich_book.epub", "pdf"),
    ("rich_report.docx", "png"),
    ("rich_report.docx", "pdf"),
    ("rich_report.docx", "html"),
    ("rich_report.docx", "epub"),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name, target in CANDIDATES:
            source = ROOT / "tests" / "fixtures" / name
            pair = run_pair(source, target, work)
            if not pair.ok:
                print(f"ERR  {name:<18} -> {target:<5} {pair.error}")
                continue
            b, a = pair.before, pair.after

            def ratio(field_name: str) -> str:
                before_val = getattr(b, field_name)
                after_val = getattr(a, field_name)
                if before_val == 0:
                    return "n/a" if after_val == 0 else f"+{after_val}"
                return f"{100 * after_val / before_val:.0f}%"

            print(
                f"ok   {name:<18} -> {target:<5} "
                f"words {ratio('words'):<5} ({a.words}/{b.words}) "
                f"img {a.images}/{b.images} "
                f"pages {a.pages}/{b.pages} "
                f"styled {a.styled_runs}/{b.styled_runs}"
            )


if __name__ == "__main__":
    main()
