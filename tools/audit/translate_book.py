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
        --model google/gemma-4-e4b --workers 7 --pages-per-chunk 8
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

#: LM Studio 7 paralel slot kapasitesine uygun varsayılan işçi sayısı / Default worker count matching LM Studio's 7 parallel slots
# The fallback when the tunable cannot be read. It matches `translation.workers`
# (2): one local GPU sharing its context across seven requests is a worse first run
# than a modest two, and the user raises it when the server has the slots.
DEFAULT_WORKERS = 2


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
        # The project is the record of what was sent, what came back and what was flagged; the
        # lossless audit reads it instead of re-reading (and re-OCRing) the source.
        "--save-project", str(out.with_suffix(".lkproj")),
    ]
    if args.timeout:
        command += ["--timeout", str(args.timeout)]
    if args.layout_detector:
        command.append("--layout-detector")
    if getattr(args, "preserve_references", False):
        # Kaynakça koruma bayrağını ilet / Forward bibliography protection flag
        command.append("--preserve-references")
    if getattr(args, "fit_mode", None):
        command += ["--fit-mode", args.fit_mode]
    started = time.time()
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - started
    # The whole log is kept: the summary below drops retries and passthrough reports, which is
    # exactly what explains a paragraph left in English.
    out.with_suffix(".log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0 and "nothing translatable found" in proc.stdout + proc.stderr:
        # A blank page, or a plate with no text, translates to itself. The CLI rightly refuses a
        # whole document with nothing to translate, but inside a book such a page must still be
        # in the output - 6 of Electricity in Agriculture's 148 pages held the merge back.
        _keep_as_is(chunk, out)
        return out, 0, f"{elapsed:6.0f}s | nothing to translate - page kept as it is"
    lines = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if any(token in line for token in _INTERESTING)
    ]
    return out, proc.returncode, f"{elapsed:6.0f}s | " + " | ".join(lines[-4:])


def _keep_as_is(chunk: Path, out: Path) -> None:
    """Copy a page with no translatable text to the output, with a project the audit can read."""
    import shutil

    from layoutkeep.core.docir import save_project
    from layoutkeep.readers.pdf_reader import read_pdf

    shutil.copyfile(chunk, out)
    save_project(read_pdf(chunk), out.with_suffix(".lkproj"))


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
    # Windows konsolunda Unicode/Türkçe kodlama hatalarını önler / Prevent Windows console Unicode encoding errors
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("_artifacts/book"))
    parser.add_argument("--to", default="tr")
    parser.add_argument("--from", default="en")
    parser.add_argument("--model", required=True)
    # Windows IPv6 gecikmesini önlemek için 127.0.0.1 / Use 127.0.0.1 to avoid Windows IPv6 SynSent timeout
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    try:
        from layoutkeep.core import tunables
        configured_workers = int(tunables.get("translation.workers", DEFAULT_WORKERS))
    except (ImportError, KeyError, ValueError, TypeError):
        configured_workers = DEFAULT_WORKERS

    parser.add_argument(
        "--workers",
        type=int,
        default=configured_workers,
        help=f"concurrent worker count (default: {configured_workers})",
    )
    parser.add_argument("--pages-per-chunk", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=0.0)
    parser.add_argument("--layout-detector", action="store_true")
    parser.add_argument("--limit-chunks", type=int, default=0, help="stop after N chunks (smoke test)")
    parser.add_argument(
        "--resume", action="store_true",
        help="skip chunks whose output already exists, so an interrupted run continues",
    )
    parser.add_argument(
        "--preserve-references", action="store_true",
        help="preserve bibliography and citation blocks untranslated",
    )
    parser.add_argument(
        "--fit-mode", default=None, choices=["strict", "reflow"],
        help="forward the CLI's fitting mode; omit to use the application's default",
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
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            index = futures[future]
            _out, code, tail = future.result()
            if code != 0:
                failures += 1
            status = "ok " if code == 0 else "FAIL"
            # Wall time per finished chunk ALREADY reflects the workers running at once, so
            # dividing it by the worker count again double-counts the parallelism. The first
            # version did, and reported "~92 min left" on a run with about six hours to go.
            # What is left is the remaining rounds - ceil(remaining / workers) - at the observed
            # wall time per round.
            elapsed = time.time() - started
            rounds_done = max(1, -(-done // args.workers))
            per_round = elapsed / rounds_done
            rounds_left = -(-(len(chunks) - done) // args.workers)
            left = rounds_left * per_round
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
