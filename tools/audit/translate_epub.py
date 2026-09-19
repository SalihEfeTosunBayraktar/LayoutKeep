"""Translate a long EPUB document by splitting chapters into chunks and running them concurrently.

Uzun EPUB kitaplarını bölüm bazında parçalayarak eşzamanlı (paralel) işleyen ve
çıktıyı kayıpsız birleştiren kampanya denetim ve çeviri aracı.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import subprocess
import sys
import time
from pathlib import Path

from layoutkeep.core.docir import Document, Page, load_project, save_project
from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.writers.epub_writer import write_epub

_INTERESTING = ("segments", "fitting", "review", "wrote", "error", "Error", "Traceback", "references")

#: LM Studio 7 paralel slot kapasitesine uygun varsayılan işçi sayısı / Default worker count matching LM Studio's 7 parallel slots
DEFAULT_WORKERS = 7


def split_epub_chapters(src: Path, work: Path, chapters_per_chunk: int) -> list[tuple[int, Path]]:
    # EPUB sayfalarını/bölümlerini bağımsız parçalara böler / Splits EPUB pages/chapters into chunks
    work.mkdir(parents=True, exist_ok=True)
    doc = read_epub(src)
    chunks: list[tuple[int, Path]] = []
    total_pages = len(doc.pages)

    for index, start in enumerate(range(0, total_pages, chapters_per_chunk)):
        chunk_pages = doc.pages[start : start + chapters_per_chunk]
        chunk_path = work / f"chunk_{index:04d}.lkproj"
        if not chunk_path.exists():
            chunk_doc = Document(
                pages=chunk_pages,
                source_path=str(src),
                source_format="epub",
                source_lang=doc.source_lang,
                target_lang=doc.target_lang,
            )
            save_project(chunk_doc, chunk_path)
        chunks.append((index, chunk_path))

    return chunks


def translate_epub_chunk(chunk: Path, out: Path, args: argparse.Namespace) -> tuple[Path, int, str]:
    # Tek bir EPUB parçası için CLI çevirisini çalıştırır / Runs CLI translation for one EPUB chunk
    if out.exists() and args.resume:
        return out, 0, "skipped (already translated)"

    command = [
        sys.executable, "-m", "layoutkeep.cli", "translate", str(chunk),
        "--to", args.to, "--from", getattr(args, "from"),
        "--provider", "openai", "--base-url", args.base_url, "--model", args.model,
        "-o", str(out),
        "--save-project", str(out),
    ]
    if args.timeout > 0:
        command += ["--timeout", str(args.timeout)]
    if getattr(args, "preserve_references", False):
        command.append("--preserve-references")

    started = time.time()
    proc = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    elapsed = time.time() - started

    log_path = out.with_suffix(".log")
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")

    if proc.returncode != 0 and "nothing translatable found" in proc.stdout + proc.stderr:
        # Boş veya çevrilemez bölümü olduğu gibi korur / Keeps non-translatable chapter as is
        import shutil
        shutil.copyfile(chunk, out)
        return out, 0, f"{elapsed:6.0f}s | nothing to translate - kept as is"

    lines = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if any(token in line for token in _INTERESTING)
    ]
    summary_tail = " | ".join(lines[-3:]) if lines else "tamamlandı / completed"
    return out, proc.returncode, f"{elapsed:6.0f}s | {summary_tail}"


def merge_epub_chunks(parts: list[Path], src_epub: Path, out_epub: Path) -> int:
    # Çevrilen parçaları tek bir EPUB dokümanında birleştirir / Merges translated chunks back into EPUB
    merged_pages: list[Page] = []
    source_lang = "en"
    target_lang = "tr"

    for part in parts:
        chunk_doc = load_project(part)
        if chunk_doc.source_lang:
            source_lang = chunk_doc.source_lang
        if chunk_doc.target_lang:
            target_lang = chunk_doc.target_lang
        merged_pages.extend(chunk_doc.pages)

    final_doc = Document(
        pages=merged_pages,
        source_path=str(src_epub),
        source_format="epub",
        source_lang=source_lang,
        target_lang=target_lang,
    )

    out_epub.parent.mkdir(parents=True, exist_ok=True)
    proj_path = out_epub.with_suffix(".lkproj")
    save_project(final_doc, proj_path)
    write_epub(final_doc, src_epub, out_epub)
    return len(merged_pages)


def main() -> int:
    # Komut satırı giriş noktası / CLI entry point for parallel EPUB runner
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="source EPUB path")
    parser.add_argument("--out", type=Path, required=True, help="target output EPUB path")
    parser.add_argument("--work", type=Path, default=Path("_artifacts/epub_work"), help="work folder")
    parser.add_argument("--to", default="tr", help="target language code")
    parser.add_argument("--from", default="en", help="source language code")
    parser.add_argument("--model", required=True, help="LLM model identifier")
    # Windows IPv6 gecikmesini önlemek için 127.0.0.1 / Use 127.0.0.1 to avoid Windows IPv6 SynSent timeout
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1", help="API base URL")
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
    parser.add_argument("--chapters-per-chunk", type=int, default=4, help="chapters per chunk")
    parser.add_argument("--timeout", type=float, default=0.0, help="per request timeout")
    parser.add_argument("--limit-chunks", type=int, default=0, help="stop after N chunks")
    parser.add_argument("--preserve-references", action="store_true", help="protect references")
    parser.add_argument("--resume", action="store_true", help="skip already translated chunks")
    args = parser.parse_args()

    work = args.work
    (work / "src").mkdir(parents=True, exist_ok=True)
    (work / "out").mkdir(parents=True, exist_ok=True)

    chunks = split_epub_chapters(args.input, work / "src", args.chapters_per_chunk)
    if args.limit_chunks:
        chunks = chunks[: args.limit_chunks]

    print(
        f"{len(chunks)} EPUB chunks ({args.chapters_per_chunk} ch/chunk), {args.workers} workers",
        flush=True,
    )

    started = time.time()
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(translate_epub_chunk, path, work / "out" / f"t_{index:04d}.lkproj", args): index
            for index, path in chunks
        }
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            index = futures[future]
            _out, code, tail = future.result()
            if code != 0:
                failures += 1
            status = "ok " if code == 0 else "FAIL"
            elapsed = time.time() - started
            rounds_done = max(1, math.ceil(done / args.workers))
            rounds_left = math.ceil((len(chunks) - done) / args.workers)
            left = rounds_left * (elapsed / rounds_done)
            print(
                f"[{done}/{len(chunks)}] {status} chunk {index:04d} {tail} (~{left / 60:.0f}m left)",
                flush=True,
            )

    outputs = [work / "out" / f"t_{index:04d}.lkproj" for index, _ in chunks]
    missing = [p for p in outputs if not p.exists()]
    if missing:
        print(f"{len(missing)} chunk(s) produced no output; cannot merge incomplete document")
        return 1

    chapters = merge_epub_chunks(outputs, args.input, args.out)
    print(
        f"merged {len(outputs)} chunks -> {args.out} ({chapters} chapters) in {(time.time() - started) / 60:.1f} min"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
