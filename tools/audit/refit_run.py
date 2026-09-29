"""Re-fit a recorded run with the current code, write it again, and audit it. Reads only.

WHY THIS EXISTS: `fit_probe.py` re-runs the fitting pass but never writes, so it cannot say what
the page looks like; `rewrite_run.py` re-runs the writer but keeps the fitting verdicts the old run
recorded, so it cannot say what the *fit* would decide today. A change inside `fitting/` moves the
verdict, and a change inside `writers/` moves the drawing, and the user's bar (blocks drawn with the
page's shape intact) depends on both. This runs the pair the application runs - fit, then write -
over a recorded run whose translations are already on disk, and audits the result with the same
criteria as the bench. No model is called: the re-translation step returns the text already in hand,
which is the honest stand-in for a model that has nothing shorter to offer.

The recorded project holds the *post-fit* document, so a block that overflowed sits at the
readability floor with its size already multiplied by `min_scale`. Re-fitting it would let it shrink
a second time and hide the very flag under measurement. `--restore-sizes` undoes exactly that for
the flagged blocks (an overflow's scale is always `min_scale`, so the division is exact), which
reproduces the recorded run's own overflow counts - the run log prints them.

    python tools/audit/refit_run.py <run-dir> [<dest-dir>] --to en --restore-sizes
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")

from layoutkeep.core import tunables  # noqa: E402
from layoutkeep.core.docir import (  # noqa: E402
    Segment,
    load_project,
    save_project,
    segments_from_document,
)
from layoutkeep.fitting.fit import FitMode  # noqa: E402
from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass  # noqa: E402
from layoutkeep.writers.pdf_writer import write_pdf  # noqa: E402

#: The sentence both front-ends write when the fit gives up (`ui/strings.REVIEW_FIT_FAILED`).
FIT_FAILED = "çeviri kutuya sığmadı"
FIT_FAILED_LONG = "çeviri kutuya sığmadı, küçültme yetmedi"


def clear_fit_flags(doc) -> int:
    """Drop the fit's own verdict from a recorded project, so the run shows today's decision.

    The project carries the *old* run's flag, and a block the current pass does not judge at all
    (its text is unchanged, so there is nothing to fit) would keep a flag this code would never
    raise. Both arms of an A/B must therefore start from the same clean slate.
    """
    cleared = 0
    for _page, block in doc.iter_blocks():
        if FIT_FAILED in (block.review_reason or ""):
            block.review_reason = ""
            block.needs_review = False
            cleared += 1
    return cleared


def restore_sizes(doc, factor: float) -> int:
    """Undo the floor-shrink on every block the fit flagged as an overflow."""
    restored = 0
    for _page, block in doc.iter_blocks():
        if FIT_FAILED in (block.review_reason or ""):
            for line in block.lines:
                for span in line.spans:
                    span.style.size /= factor
            restored += 1
    return restored


def _segments_for(doc) -> list[Segment]:
    """Every translatable block, with the text the run recorded as its translation."""
    segments = segments_from_document(doc)
    by_id = {block.id: block for _page, block in doc.iter_blocks()}
    kept: list[Segment] = []
    for segment in segments:
        block = by_id.get(segment.block_id)
        if block is None or not block.text.strip():
            continue
        segment.target = block.text
        kept.append(segment)
    return kept


def refit_chunk(project: Path, source: Path, out: Path, target_lang: str, *, restore: bool) -> dict:
    doc = load_project(project)
    if restore:
        restore_sizes(doc, float(tunables.get("fit.min_scale")))
    clear_fit_flags(doc)
    segments = _segments_for(doc)
    layers: Counter = Counter()
    if segments:
        def on_fitted(seg, block, result) -> None:
            seg.target = result.text
            layers[str(result.layer)] += 1
            if result.needs_review:
                layers["flagged"] += 1
                layers["role:" + block.role.value] += 1
                layers["cause:" + (result.review_reason or "overflow")] += 1
                block.needs_review = True
                block.review_reason = result.review_reason or FIT_FAILED_LONG
                seg.needs_review = True
                seg.review_reason = block.review_reason
            apply_scale(block, result.scale)

        fit_pdf_pass(
            doc,
            segments,
            retranslate=lambda seg, _budget: seg.target,
            mode=FitMode.STRICT,
            target_lang=target_lang,
            on_fitted=on_fitted,
        )
    # The audit reads the project for the block list, the sources and the fit's own verdict, so the
    # re-fitted document has to be written back - otherwise `D1` would report the old run's flags.
    save_project(doc, project)
    write_pdf(doc, source, out)
    return dict(layers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    parser.add_argument("dest", type=Path, nargs="?")
    parser.add_argument("--to", default="tr", help="target language of the run")
    parser.add_argument("--restore-sizes", action="store_true",
                        help="undo the floor-shrink the recorded fit applied to flagged blocks")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="pin a setting for this arm (repeatable)")
    args = parser.parse_args()

    for pair in args.set:
        key, _, value = pair.partition("=")
        spec = tunables.definition(key)  # a typo fails here, before the run
        tunables.set_value(key, value.lower() in ("1", "true", "yes") if spec.kind == "bool" else value)

    run: Path = args.run
    dest: Path = args.dest or run.with_name(run.name + "_refit")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run, dest)

    layers: Counter = Counter()
    for project in sorted((dest / "out").glob("t_*.lkproj")):
        index = project.stem.split("_")[1]
        source = dest / "src" / f"chunk_{index}.pdf"
        if not source.exists():
            source = dest / "src" / f"{index}.pdf"
        if not source.exists():
            print(f"!! no source for {project.name}")
            continue
        counts = refit_chunk(project, source, project.with_suffix(".pdf"), args.to,
                             restore=args.restore_sizes)
        layers.update(counts)
        print(f"  {project.stem}  {counts}")
    print(f"fit over {dest.name}: " + ", ".join(
        f"{key}={value}" for key, value in sorted(layers.items()) if not key.startswith(("role:", "cause:"))))
    for prefix in ("role:", "cause:"):
        by_kind = {key[len(prefix):]: value for key, value in layers.items() if key.startswith(prefix)}
        if by_kind:
            print(f"  flagged by {prefix.rstrip(':')}: " + ", ".join(
                f"{name}={count}" for name, count in sorted(by_kind.items(), key=lambda kv: -kv[1])))

    result = subprocess.run(
        [sys.executable, "tools/audit/lossless_audit.py", "--work", str(dest), "--to", args.to],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(result.stdout + result.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
