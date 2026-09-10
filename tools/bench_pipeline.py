"""Time a whole translation, phase by phase, and say where the time went.

"It takes a while" is not a measurement. This runs one document through the real pipeline and
records what each stage cost, how much text each stage handled, and - for a paid provider - how
much quota the run consumed. The numbers land in a JSON file so a later run can be compared
against an earlier one rather than against a memory of it.

    .venv/Scripts/python.exe tools/bench_pipeline.py docs/samples/academic_paper.pdf fake
    .venv/Scripts/python.exe tools/bench_pipeline.py docs/samples/academic_paper.pdf deepl --out out.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@dataclass
class Phase:
    name: str
    seconds: float
    detail: str = ""


@dataclass
class Run:
    document: str
    provider: str
    pages: int = 0
    blocks: int = 0
    segments: int = 0
    characters: int = 0
    images: int = 0
    flagged: int = 0
    requests: int = 0
    quota_used: int = 0
    phases: list[Phase] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(p.seconds for p in self.phases)


class _CountingProvider:
    """Passes translation through and keeps a running total of what the provider actually did."""

    def __init__(self, provider, inner) -> None:
        self._provider = provider
        self._inner = inner
        self.requests = 0

    def translate(self, segments, **kwargs):
        result = self._provider.translate(segments, **kwargs)
        self.requests += int(getattr(self._inner, "last_stats", {}).get("requests", 0))
        return result

    def __getattr__(self, name):
        return getattr(self._provider, name)


def _provider(kind: str, target_lang: str):
    """The provider, and a callable that reports how many requests it made."""
    from layoutkeep.providers.protected import ProtectedProvider

    if kind == "fake":
        from layoutkeep.providers.fake import FakeProvider

        inner = FakeProvider()
        return ProtectedProvider(inner), lambda: 0, lambda: 0

    if kind == "deepl":
        from layoutkeep.providers.deepl import DeepLProvider
        from layoutkeep.ui import keyring_store

        key = keyring_store.get_api_key("deepl")
        if not key:
            raise SystemExit("no DeepL key stored - configure one in the application first")
        inner = DeepLProvider(key, timeout=120.0)

        # `last_stats` describes the most recent `translate()` call, not the run. The fitting
        # pass asks for single segments again one at a time, so reading it at the end reported
        # "1 request" for a job that had made a hundred. Counted here instead.
        counted = _CountingProvider(ProtectedProvider(inner), inner)

        def requests() -> int:
            return counted.requests

        def quota() -> int:
            import re

            reply = inner.check_connection()
            match = re.search(r"([\d,]+)\s*/", reply)
            return int(match.group(1).replace(",", "")) if match else 0

        return counted, requests, quota

    raise SystemExit(f"unknown provider: {kind}")


def _fit(doc, segments, provider, target_lang: str) -> int:
    """Run the same fitting pass the CLI and the desktop app run.

    Leaving it out was measuring a pipeline the product never runs: no font is shrunk to its
    box, no over-long translation is asked for again shorter, and nothing is ever flagged for
    review - which is why this reported zero flagged segments on documents that plainly had
    some. Returns how many segments the pass changed.
    """
    from layoutkeep.core.docir import Segment
    from layoutkeep.fitting import FitMode
    from layoutkeep.fitting.fit import FitLayer
    from layoutkeep.fitting.pdf_pass import apply_scale, fit_pdf_pass

    def retranslate(segment: Segment, budget: int) -> str:
        segment.max_len = budget
        again = provider.translate([segment], src_lang="en", tgt_lang=target_lang)
        return again[0].target if again and again[0].target else segment.target

    changed = 0

    def on_fitted(seg, block, result) -> None:
        nonlocal changed
        seg.target = result.text
        if result.layer is not FitLayer.AS_IS:
            changed += 1
        if result.needs_review:
            seg.needs_review = True
            seg.review_reason = "çeviri kutuya sığmadı, küçültme yetmedi"
            block.needs_review = True
            block.review_reason = seg.review_reason
        apply_scale(block, result.scale)

    fit_pdf_pass(
        doc,
        segments,
        retranslate=retranslate,
        mode=FitMode.STRICT,
        target_lang=target_lang,
        on_fitted=on_fitted,
    )
    return changed


def run(document: Path, provider_kind: str, out_path: Path | None, target_lang: str) -> Run:
    from layoutkeep.core.docir import apply_segments, segments_from_document
    from layoutkeep.writers.converter import read_any_document, write_any_document

    result = Run(document=document.name, provider=provider_kind)
    provider, requests, quota = _provider(provider_kind, target_lang)
    before_quota = quota()

    started = time.monotonic()
    doc = read_any_document(document)
    result.phases.append(
        Phase("read", time.monotonic() - started, f"{len(doc.pages)} pages")
    )
    result.pages = len(doc.pages)
    result.blocks = sum(len(page.blocks) for page in doc.pages)
    result.images = sum(len(page.images) for page in doc.pages)

    started = time.monotonic()
    segments = segments_from_document(doc)
    result.segments = len(segments)
    result.characters = sum(len(s.source) for s in segments)
    result.phases.append(
        Phase("segment", time.monotonic() - started, f"{result.segments} segments")
    )

    started = time.monotonic()
    translated = provider.translate(segments, src_lang="en", tgt_lang=target_lang)
    result.phases.append(
        Phase("translate", time.monotonic() - started, f"{result.characters:,} chars")
    )
    started = time.monotonic()
    fitted = _fit(doc, translated, provider, target_lang)
    result.flagged = sum(1 for s in translated if s.needs_review)
    result.phases.append(Phase("fit", time.monotonic() - started, f"{fitted} shrunk or reworded"))
    result.requests = requests()

    started = time.monotonic()
    apply_segments(doc, translated)
    result.phases.append(Phase("apply", time.monotonic() - started))

    if out_path is not None:
        started = time.monotonic()
        write_any_document(doc, document, out_path)
        size = out_path.stat().st_size // 1024
        result.phases.append(
            Phase(f"write {out_path.suffix.lstrip('.')}", time.monotonic() - started, f"{size:,} KB")
        )

    after_quota = quota()
    result.quota_used = max(0, after_quota - before_quota)
    return result


def report(result: Run) -> str:
    lines = [
        f"{result.document} - {result.provider}",
        (
            f"{result.pages} pages, {result.blocks} blocks, {result.segments} segments, "
            f"{result.characters:,} characters, {result.images} images"
        ),
        "",
        f"{'phase':<14}{'seconds':>10}{'share':>9}   detail",
    ]
    total = result.total or 1.0
    for phase in result.phases:
        lines.append(
            f"{phase.name:<14}{phase.seconds:>10.1f}{phase.seconds / total * 100:>8.0f}%   "
            f"{phase.detail}"
        )
    lines.append(f"{'total':<14}{result.total:>10.1f}{100:>8.0f}%")
    lines.append("")
    lines.append(
        f"flagged segments: {result.flagged} / {result.segments}"
        + (f" | provider requests: {result.requests}" if result.requests else "")
        + (f" | quota used: {result.quota_used:,} chars" if result.quota_used else "")
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document")
    parser.add_argument("provider", choices=["fake", "deepl"])
    parser.add_argument("--out", help="also write the translated document here")
    parser.add_argument("--to", default="tr", dest="target_lang")
    parser.add_argument("--json", help="write the measurements here as JSON")
    args = parser.parse_args()

    result = run(
        Path(args.document),
        args.provider,
        Path(args.out) if args.out else None,
        args.target_lang,
    )
    print(report(result))

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        print(f"\n{target} yazildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
