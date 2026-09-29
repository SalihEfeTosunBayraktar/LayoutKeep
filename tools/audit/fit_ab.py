"""A/B a fitting change on the written page: re-fit a recorded run, write it, audit it.

WHY THIS EXISTS: `fit_probe.py` counts the ladder's verdicts, which says whether a step fires but
not what it costs on the page. The cost of a leading step is a squeezed page (D3) and the benefit
is text that is no longer flagged (D1), and both are measured on the *written* PDF - so this tool
does what a front-end does (fit, then apply the result to the block's spans, then write) and hands
the result to `lossless_audit.py`.

What it can and cannot answer: the saved project holds the post-fit document, so blocks that
already fitted are re-shrunk here and their pages differ from the recorded run's. That is the same
in both arms of the comparison, so it cancels; the population a leading step actually touches -
blocks that ended as overflow, sitting at the readability floor - is reproduced faithfully,
because the floor is where they already are.

Usage: python tools/audit/fit_ab.py <run-dir> [<dest-dir>] [--limit N]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "src")

from layoutkeep.core.docir import load_project, segments_from_document  # noqa: E402
from layoutkeep.fitting.fit import FitMode  # noqa: E402
from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass  # noqa: E402

try:  # the "before" arm runs this script against a tree where the leading step does not exist
    from layoutkeep.fitting.pdf_pass import apply_line_height  # noqa: E402
except ImportError:

    def apply_line_height(block, line_height) -> None:  # type: ignore[misc]
        """No leading step in that tree, so there is nothing to write back."""

from layoutkeep.writers.pdf_writer import write_pdf  # noqa: E402


def _rewrite(dest: Path, limit: int | None) -> int:
    written = 0
    projects = sorted((dest / "out").glob("t_*.lkproj"))
    for project in projects[:limit] if limit else projects:
        out_pdf = project.with_suffix(".pdf")
        number = project.stem.removeprefix("t_")
        source = dest / "src" / f"chunk_{number}.pdf"
        if not source.exists():
            source = dest / "src" / f"{number}.pdf"
        if not source.exists():
            print(f"!! no source for {project.name}")
            continue
        doc = load_project(project)
        segments = segments_from_document(doc)
        by_id = {block.id: block for _page, block in doc.iter_blocks()}
        kept = []
        for segment in segments:
            block = by_id.get(segment.block_id)
            if block is None or not block.text.strip():
                continue
            segment.target = block.text
            kept.append(segment)

        def on_fitted(_segment, block, result) -> None:
            # Exactly what cli.py and ui/worker.py do with a verdict - the point of the exercise
            # is to measure the pipeline's behaviour, not this tool's.
            apply_scale(block, result.scale)
            # getattr, not attribute access: the "before" arm's FitResult has no line_height at
            # all, and evaluating the argument would raise before the no-op could be called.
            apply_line_height(block, getattr(result, "line_height", None))

        fit_pdf_pass(
            doc,
            kept,
            retranslate=lambda segment, _budget: segment.target,
            mode=FitMode.STRICT,
            target_lang="tr",
            on_fitted=on_fitted,
        )
        write_pdf(doc, source, out_pdf)
        written += 1
    return written


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit":
            limit = int(sys.argv[i + 1])
    run = Path(args[0])
    dest = Path(args[1]) if len(args) > 1 else run.with_name(run.name + "_fitab")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run, dest)
    print(f"{_rewrite(dest, limit)} chunk yazıldı -> {dest}")
    if limit:
        # The copy brought every chunk the live run had already written. Chunks this tool did not
        # rewrite still carry that run's fitting, and auditing them would mix two arms into one
        # number - so they leave the copy (the recorded run keeps them).
        kept = {f"t_{i:04d}" for i in range(limit)}
        dropped = 0
        for path in sorted((dest / "out").glob("t_*.*")):
            if path.stem not in kept:
                path.unlink()
                dropped += 1
        print(f"{dropped} parça kopyadan çıkarıldı (yeniden yazılmayanlar)")
    return subprocess.call(
        [sys.executable, "tools/audit/lossless_audit.py", "--work", str(dest), "--to", "tr"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
