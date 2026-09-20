"""Re-run the fitting pass over a recorded run and count what each block ended as.

WHY THIS EXISTS: `rewrite_run.py` re-runs the *writer*, so it can judge a writer change and nothing
else. A change inside `fitting/` (the ladder: as-is, shrink, retranslate, overflow) is decided
before the writer is called, so the only honest model-free instrument is to re-run that pass itself
over a run whose translations are already recorded. This is that instrument.

What it can and cannot answer: the saved project holds the *post-fit* document, so for a block that
already fitted, re-fitting is a no-op (as-is) and the probe says nothing new about it. The blocks it
does speak about are the ones that ended as overflow - they sit at the readability floor in the
saved project, which is exactly the state the ladder's later steps see, so a step added after the
shrink is measured on precisely the inputs it would meet in a real run.

`retranslate` is a no-op here: no model is available, and returning the same text is the honest
stand-in (the ladder then continues past the retranslate step, as it would when the model cannot
help). The step under measurement runs *before* it.

Usage: python tools/audit/fit_probe.py <run-dir> [<run-dir> ...]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")

from layoutkeep.core.docir import Segment, load_project, segments_from_document  # noqa: E402
from layoutkeep.fitting.fit import FitMode  # noqa: E402
from layoutkeep.fitting.pdf_pass import fit_pdf_pass  # noqa: E402


def _segments_for(doc) -> list[Segment]:
    """Every translatable block, with the translation this run recorded as its target.

    `segments_from_document` is the pipeline's own builder (it also attaches the neighbouring
    context the model saw); the only thing missing from a saved project is the target, which is
    the block's own text by the time the run is on disk.
    """
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


def probe(run: Path) -> Counter:
    layers: Counter = Counter()
    for project in sorted((run / "out").glob("t_*.lkproj")):
        doc = load_project(project)
        segments = _segments_for(doc)
        if not segments:
            continue
        verdicts: list[object] = []
        fit_pdf_pass(
            doc,
            segments,
            retranslate=lambda seg, _budget: seg.target,
            mode=FitMode.STRICT,
            target_lang="tr",
            on_fitted=lambda _seg, _block, result: verdicts.append(result),
        )
        for result in verdicts:
            layers[str(result.layer)] += 1
            if getattr(result, "needs_review", False):
                layers["flagged"] += 1
    return layers


def main() -> int:
    for name in sys.argv[1:]:
        run = Path(name)
        layers = probe(run)
        total = sum(v for k, v in layers.items() if k != "flagged")
        print(f"{run.name:34} blok={total:5}  " + "  ".join(
            f"{key}={layers[key]}" for key in sorted(layers)
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
