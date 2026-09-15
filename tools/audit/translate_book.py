"""Translate a long document by splitting it into page chunks and running them concurrently.

Why this exists: a 524-page scan is ~18,000 translatable segments. Measured against
gemma-4-e4b on LM Studio, one `layoutkeep translate` process sustains roughly 0.28 segments a
second, which puts the whole book at about 17 hours. The limit is not the reader (OCR runs at
~2.3 s/page) and not the writer - it is that the provider layer sends one request at a time and
waits.

Rather than making `providers/` concurrent - which would entangle with `AdaptiveBatchSize`, whose
sizing feedback assumes it sees one batch's timing after another - this drives the *existing,
tested* pipeline from outside: split the PDF, run N translate processes against a server loaded
with N parallel slots, then concatenate the outputs. Each chunk goes through exactly the code
path a normal single-file run takes, so nothing about the result depends on this script beyond
where the page boundaries fall.

Chunks are cut on page boundaries, so no block is ever split across two processes.

    python tools/audit/translate_book.py INPUT.pdf --out OUT.pdf \
        --model google/gemma-4-e4b --workers 4 --pages-per-chunk 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

#: Per-chunk log lines worth surfacing; the rest of the CLI's output is noise at this level.
_INTERESTING = ("segments", "fitting", "review", "wrote", "error", "Error", "Traceback")


def split_pages(src: Path, work: Path, pages_per_chunk: int) -> list[tuple[int, Path]]:
    """Cut `src` into page-aligned chunks. Returns (index, path) in document order."""
    chunks: list[tuple[int, Path]] = []
    with pymupdf.open(str(src)) as book:
        total = book.page_count
        for index, start in enumerate(range(0, total, pages_per_chunk)):
            end = min(start + pages_per_chunk - 1, total - 1)
            out = work / f"chunk_{index:04d}.pdf"
            if not out.exists():
                part = pymupdf.open()
                part.insert_pdf(book, from_page=start, to_page=end)
                part.save(str(out))
                part.close()
            chunks.append((index, out))
    return chunks


def translate_chunk(chunk: Path, out: Path, args: argparse.Namespace) -> tuple[Path, int, str]:
    """Run one `layoutkeep translate` for one chunk. Returns (output, returncode, tail)."""
    if out.exists() and args.resume:
        return out, 0, "skipped (already translated)"
    command = [
        sys.executable, "-m", "layoutkeep.cli", "translate", str(chunk),
        "--to", args.to, "--from", getattr(args, "from"),
        "--provider", "openai", "--base-url", args.base_url, "--model", args.model,
        "-o", str(out),
    ]
    if args.timeout:
        command += ["--timeout", str(args.timeout)]
    started = time.time()
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    lines = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if any(token in line for token in _INTERESTING)
    ]
    return out, proc.returncode, f"{elapsed:6.0f}s | " + " | ".join(lines[-4:])


def merge(parts: list[Path], out: Path) -> int:
    """Concatenate translated chunks back into one document, in order."""
    merged = pymupdf.open()
    for part in parts:
        with pymupdf.open(str(part)) as chunk:
            merged.insert_pdf(chunk)
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.save(str(out), garbage=4, deflate=True)
    pages = merged.page_count
    merged.close()
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("_artifacts/book"))
    parser.add_argument("--to", default="tr")
    parser.add_argument("--from", default="en")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://localhost:1234/v1")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pages-per-chunk", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=0.0)
    parser.add_argument("--limit-chunks", type=int, default=0, help="stop after N chunks (smoke test)")
    parser.add_argument(
        "--resume", action="store_true",
        help="skip chunks whose output already exists, so an interrupted run continues",
    )
    args = parser.parse_args()

    work = args.work
    (work / "src").mkdir(parents=True, exist_ok=True)
    (work / "out").mkdir(parents=True, exist_ok=True)

    chunks = split_pages(args.input, work / "src", args.pages_per_chunk)
    if args.limit_chunks:
        chunks = chunks[: args.limit_chunks]
    print(f"{len(chunks)} chunks of up to {args.pages_per_chunk} pages, {args.workers} workers", flush=True)

    outputs: list[Path] = []
    failures = 0
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(translate_chunk, path, work / "out" / f"t_{index:04d}.pdf", args): index
            for index, path in chunks
        }
        done = 0
        for future in concurrent.futures.as_completed(futures):
            index = futures[future]
            out, code, tail = future.result()
            done += 1
            if code != 0:
                failures += 1
            status = "ok " if code == 0 else "FAIL"
            rate = (time.time() - started) / done
            left = (len(chunks) - done) * rate / max(1, args.workers)
            print(
                f"[{done}/{len(chunks)}] {status} chunk {index:04d} {tail}  "
                f"(~{left / 60:.0f} min left)",
                flush=True,
            )

    outputs = [work / "out" / f"t_{index:04d}.pdf" for index, _ in chunks]
    missing = [p for p in outputs if not p.exists()]
    if missing:
        print(f"{len(missing)} chunk(s) produced no output; not merging a document with holes")
        return 1

    pages = merge(outputs, args.out)
    print(f"merged {len(outputs)} chunks -> {args.out} ({pages} pages) in {(time.time() - started) / 60:.1f} min")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
