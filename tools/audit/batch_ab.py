"""Does starting the adaptive batch bigger actually help? Measured, not assumed.

The provider's batch size starts small and grows while replies hold together; per-request overhead
dominates the cost of a local model (measured: five segments in one request cost 60s, one segment
at a time cost 32.7s each - ~2.7x per segment). So where a run *starts* is a real cost: starting at
1 pays the climb on every job, starting at 4 pays one wasted request on a model that can only hold
one segment.

This translates one page with each starting size and prints wall time, request count and how many
segments came back translated, so the default in `batch.adaptive_start_segments` rests on numbers.

    python tools/audit/batch_ab.py _artifacts/heldout/live/fresh_pdfmt_r6/src/chunk_0000.pdf
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from layoutkeep.core import tunables  # noqa: E402
from layoutkeep.core.docir import segments_from_document  # noqa: E402
from layoutkeep.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from layoutkeep.readers.pdf_reader import read_pdf  # noqa: E402


def run_once(source: Path, start: int, model: str, base_url: str) -> dict:
    """Translate the page with one starting batch size and report what it cost."""
    tunables.set_value("batch.adaptive_start_segments", start)
    document = read_pdf(source)
    segments = segments_from_document(document)
    provider = OpenAICompatProvider(model=model, base_url=base_url)
    started = time.monotonic()
    translated = provider.translate(segments, "en", "tr")
    elapsed = time.monotonic() - started
    return {
        "start": start,
        "seconds": round(elapsed, 1),
        "requests": provider._transport.requests,
        "segments": len(segments),
        "translated": sum(1 for segment in translated if segment.target.strip()),
        "per_segment_s": round(elapsed / max(1, len(segments)), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--model", default="google/gemma-4-e4b")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--starts", default="1,4")
    args = parser.parse_args()

    results = [run_once(args.source, int(start), args.model, args.base_url) for start in args.starts.split(",")]
    print(f"\n{args.source.name}, {results[0]['segments']} segments")
    print(f"{'start':>6} {'requests':>9} {'seconds':>9} {'s/segment':>10} {'translated':>11}")
    for result in results:
        print(
            f"{result['start']:>6} {result['requests']:>9} {result['seconds']:>9} "
            f"{result['per_segment_s']:>10} {result['translated']:>11}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
