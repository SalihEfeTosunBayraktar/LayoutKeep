"""Command line entry point.

Phase 0 scope: EPUB in, EPUB out, translated through an OpenAI-compatible endpoint.
The GUI (phase 1) will call the same functions, so keep the orchestration here and not in the
subcommand handlers.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from layoutkeep.core.docir import (
    Document,
    apply_segments,
    save_project,
    segments_from_document,
)
from layoutkeep.core.estimate import estimate_job, measured_expansion

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FAILED = 1


# --------------------------------------------------------------------------------------
# Lazy loading: an optional extra that is not installed must produce one clear sentence,
# not a traceback from three frames down.
# --------------------------------------------------------------------------------------


def _read_document(path: Path) -> Document:
    # Dokümanı veya görseli DocIR'e okur / Reads document or image into DocIR
    from layoutkeep.writers.converter import read_any_document

    suffix = path.suffix.lower()
    try:
        return read_any_document(path)
    except ImportError as exc:
        raise SystemExit(
            f"Required library is not available ({exc}). Please install appropriate extras."
        ) from exc
    except FileNotFoundError as exc:
        # K3: eksik/bozuk girdi traceback yerine tek cümle / Missing input → one clear sentence
        raise SystemExit(str(exc)) from None
    except ValueError as exc:
        raise SystemExit(
            f"Unsupported input type {suffix!r}. Expected document or image (.png, .jpg, .epub, .pdf, .docx, .lkproj)."
        ) from exc


def _write_document(doc: Document, source: Path, out: Path) -> list[Path]:
    # Çıktı formatına göre dokümanı yazar / Writes document according to target format
    from layoutkeep.writers.converter import write_any_document

    try:
        return write_any_document(doc, source, out)
    except ImportError as exc:
        raise SystemExit(
            f"Required library for target format is not available ({exc})."
        ) from exc
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _build_provider(args: argparse.Namespace):
    """Build the provider, wrapped in literal protection and, if requested, translation memory.

    Protection goes outermost so the memory stores the tokenised form. That is deliberate:
    "Tighten the bolts to 63 Nm" and "...to 150 Nm" tokenise to the same string, so one cached
    translation serves both and each restores its own value from its own source.
    """
    if args.provider == "fake":
        from layoutkeep.providers.fake import FakeProvider

        provider, model_id = FakeProvider(), "fake"
    elif args.provider == "deepl":
        from layoutkeep.providers.deepl import DeepLProvider

        if not args.api_key:
            raise SystemExit(
                "--api-key is required for the deepl provider. A free key ends in ':fx'."
            )
        provider = DeepLProvider(args.api_key, timeout=args.timeout or 60.0)
        model_id = f"deepl:{provider.host}"
    else:
        from layoutkeep.providers.openai_compat import OpenAICompatProvider

        if not args.model:
            raise SystemExit(
                "--model is required for the openai provider. "
                "Run 'layoutkeep models --base-url ...' to see what the server has."
            )
        provider = OpenAICompatProvider(
            base_url=args.base_url, model=args.model, api_key=args.api_key,
            timeout=args.timeout,
        )
        model_id = f"{args.base_url}:{args.model}"

    from layoutkeep.providers.protected import ProtectedProvider

    if not args.memory:
        return ProtectedProvider(provider), None

    from layoutkeep.providers.cached import CachedProvider
    from layoutkeep.providers.memory import TranslationMemory

    memory = TranslationMemory(args.memory)
    return ProtectedProvider(CachedProvider(provider, memory, model_id)), memory


# --------------------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------------------


def cmd_inspect(args: argparse.Namespace) -> int:
    """Show what the reader actually understood. This is the phase-0 debugging workhorse.

    Role misclassification (a running header read as body text, a page number read as a heading)
    is the single most common way layout-preserving translation goes wrong, and it is invisible
    until you look at the counts.
    """
    src = Path(args.input)
    doc = _read_document(src)
    segments = segments_from_document(doc)

    roles = Counter(block.role.value for _, block in doc.iter_blocks())
    chars = sum(len(s.source) for s in segments)

    print(f"file            {src.name}")
    print(f"format          {doc.source_format or src.suffix.lstrip('.')}")
    print(f"pages           {len(doc.pages)}")
    print(f"blocks          {sum(len(p.blocks) for p in doc.pages)}")
    print(f"translatable    {len(segments)} segments, {chars} chars")
    print("roles")
    for role, n in roles.most_common():
        print(f"  {role:<14} {n}")

    if args.sample:
        print(f"\nfirst {args.sample} segments")
        for seg in segments[: args.sample]:
            preview = seg.source.replace("\n", " ")
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"  [{seg.block_id}] {preview}")
    return EXIT_OK


def cmd_models(args: argparse.Namespace) -> int:
    """List what the local server has. Saves the user from guessing a model id."""
    from layoutkeep.providers.openai_compat import OpenAICompatProvider

    provider = OpenAICompatProvider(base_url=args.base_url, model="", api_key=args.api_key)
    try:
        models = provider.list_models()
    except OSError as exc:
        print(f"cannot reach {args.base_url}: {exc}")
        print("is LM Studio (port 1234) or Ollama (port 11434) running with the server enabled?")
        return EXIT_FAILED
    if not models:
        print(f"{args.base_url} answered but offers no models")
        return EXIT_FAILED
    for name in models:
        print(name)
    return EXIT_OK


def cmd_translate(args: argparse.Namespace) -> int:
    src = Path(args.input)
    out = Path(args.output) if args.output else src.with_name(
        f"{src.stem}.{args.to_lang}{src.suffix}"
    )
    if out.resolve() == src.resolve():
        raise SystemExit("Output path is the same as the input. Refusing to overwrite the source.")

    print(f"reading   {src}")
    doc = _read_document(src)
    doc.source_lang = args.from_lang
    doc.target_lang = args.to_lang

    segments = segments_from_document(doc)
    if not segments:
        print("nothing translatable found - stopping")
        return EXIT_FAILED
    print(f"segments  {len(segments)} ({sum(len(s.source) for s in segments)} chars)")

    if args.skip:
        segments = segments[args.skip :]
        print(f"skip      skipping the first {args.skip} segments")
    if args.limit:
        segments = segments[: args.limit]
        print(f"limit     translating only {len(segments)} segments")

    est = estimate_job(segments, args.from_lang, args.to_lang)
    print(f"estimate  ~{est.input_tokens:,} in + ~{est.output_tokens:,} out tokens"
          f"  (assuming {est.assumed_expansion:.2f}x expansion)")

    glossary = None
    if args.glossary:
        from layoutkeep.providers.glossary import Glossary

        glossary = Glossary.load(args.glossary)
        print(f"glossary  {len(glossary.terms)} terms from {args.glossary}")

    provider, memory = _build_provider(args)
    print(f"provider  {type(provider).__name__} model={args.model or '-'}")

    started = time.monotonic()
    try:
        translated = provider.translate(
            segments,
            src_lang=args.from_lang,
            tgt_lang=args.to_lang,
            glossary=glossary.terms if glossary else None,
        )
    except TimeoutError:
        # A large local model can spend minutes loading before it emits a single token, so this
        # is an ordinary condition rather than a fault. Say what to do about it.
        limit = f"within {args.timeout:.0f}s" if args.timeout else "in time"
        raise SystemExit(
            f"the server at {args.base_url} did not answer {limit}.\n"
            f"A large local model can take minutes to load. Try --timeout 600, "
            f"or --limit 5 first to see how long one batch really takes."
        ) from None
    except OSError as exc:
        raise SystemExit(
            f"cannot reach {args.base_url}: {exc}\n"
            f"Is LM Studio (port 1234) or Ollama (port 11434) running with its server enabled?"
        ) from None
    elapsed = time.monotonic() - started

    stats = getattr(provider, "last_stats", None)
    if stats and (stats["protected"] or stats["skipped"]):
        note = f"protect   {stats['protected']} literal values held back from the model"
        if stats["skipped"]:
            note += f", {stats['skipped']} data-only segments answered without a request"
        if stats["lost"]:
            note += f", {stats['lost']} NOT returned - those segments flagged"
        print(note)

    from layoutkeep.providers.passthrough import flag_passthrough

    handed_back = flag_passthrough(translated)
    if handed_back:
        print(f"passthrough {handed_back} segments came back untranslated - flagged for review")

    if glossary:
        translated, report = glossary.verify(translated)
        checked, honoured = report["checked"], report["honoured"]
        if checked:
            print(f"glossary  {honoured}/{checked} term occurrences honoured"
                  f"{' - rest flagged for review' if honoured < checked else ''}")

    done = sum(1 for s in translated if s.translated)
    review = sum(1 for s in translated if s.needs_review)
    cached = sum(1 for s in translated if s.from_memory)
    print(f"translated {done}/{len(translated)} in {elapsed:.1f}s"
          f"  cached={cached}  needs_review={review}")

    marker_stats = getattr(provider, "last_marker_repair_stats", None) or getattr(
        getattr(provider, "inner", None), "last_marker_repair_stats", None
    )
    if marker_stats and (marker_stats["repaired"] or marker_stats["still_mismatched"]):
        print(f"markers   {marker_stats['repaired']} segments repaired, "
              f"{marker_stats['still_mismatched']} still wrong (inline styling lost there)")

    if memory is not None:
        st = memory.stats()
        total = st["hits"] + st["misses"]
        rate = st["hits"] / total if total else 0.0
        print(f"memory    {st['hits']}/{total} hits ({rate:.0%}), {st['entries']} entries stored")

    if done == 0:
        print("no segment came back translated - not writing output")
        return EXIT_FAILED

    growth = measured_expansion(translated)
    if growth is not None:
        delta = growth - est.assumed_expansion
        print(f"length    target/source = {growth:.2f}x measured"
              f"  ({delta:+.2f} vs the {est.assumed_expansion:.2f}x assumed)")

    if src.suffix.lower() == ".pdf":
        fit_stats = _fit_pdf(doc, translated, provider, args)
        if fit_stats:
            total = sum(fit_stats.values())
            parts = " ".join(f"{k}={v}" for k, v in fit_stats.items() if v)
            print(f"fitting   {total} blocks: {parts}")
            if fit_stats.get("overflow"):
                print(f"          {fit_stats['overflow']} still overflow - flagged for review")

    orphans = apply_segments(doc, translated)
    if orphans:
        print(f"WARNING   {len(orphans)} translated segments did not match any block: "
              f"{orphans[:5]}{'...' if len(orphans) > 5 else ''}")

    written = _write_document(doc, src, out)
    if len(written) > 1:
        # An image target writes one file per page, so naming only `out` would understate it.
        print(f"wrote     {len(written)} files, {written[0]} .. {written[-1].name}")
    else:
        print(f"wrote     {out}")

    if args.save_project:
        proj = Path(args.save_project)
        save_project(doc, proj)
        print(f"project   {proj}")

    return EXIT_OK


def _fit_pdf(doc: Document, segments, provider, args) -> dict[str, int] | None:
    """Make the translated text fit its original boxes. PDF only - EPUB reflows by itself.

    Delegates to `fitting.pdf_pass`, the one pass the desktop worker runs too (a GUI that
    drifts from the CLI here is a bug, not a feature - both must fit identically).
    """
    from layoutkeep.fitting import FitMode
    from layoutkeep.fitting.pdf_pass import fit_pdf_pass

    def retranslate(segment, budget: int) -> str:
        """Ask the provider for a shorter rendering of one segment, within `budget` characters."""
        segment.max_len = budget
        again = provider.translate(
            [segment], src_lang=args.from_lang, tgt_lang=args.to_lang, glossary=None
        )
        return again[0].target if again and again[0].target else segment.target

    mode = FitMode.REFLOW if args.fit_mode == "reflow" else FitMode.STRICT

    def on_fitted(seg, block, result) -> None:
        # fit_segment is pure - it reports what would fit. Writing the result back is ours.
        seg.target = result.text
        if result.needs_review:
            seg.needs_review = True
            seg.review_reason = "çeviri kutuya sığmadı, küçültme yetmedi"
            block.needs_review = True
            block.review_reason = seg.review_reason
        _apply_scale(block, result.scale)

    return fit_pdf_pass(
        doc,
        segments,
        retranslate=retranslate,
        mode=mode,
        target_lang=args.to_lang,
        on_fitted=on_fitted,
    )


def _apply_scale(block, scale: float) -> None:
    # Ortak uygulama fitting/pdf_pass.py'de / Shared write-back lives in fitting/pdf_pass.py
    from layoutkeep.fitting.pdf_pass import apply_scale

    apply_scale(block, scale)


# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="layoutkeep",
        description="Translate documents while preserving their layout.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    insp = sub.add_parser("inspect", help="show how the reader parsed a document")
    insp.add_argument("input")
    insp.add_argument("--sample", type=int, default=0, metavar="N",
                      help="also print the first N translatable segments")
    insp.set_defaults(func=cmd_inspect)

    mdl = sub.add_parser("models", help="list the models an OpenAI-compatible server offers")
    mdl.add_argument("--base-url", default="http://localhost:1234/v1",
                     help="LM Studio defaults to port 1234, Ollama to 11434")
    mdl.add_argument("--api-key", default=None)
    mdl.set_defaults(func=cmd_models)

    tr = sub.add_parser("translate", help="translate a document")
    tr.add_argument("input")
    tr.add_argument("--to", dest="to_lang", required=True, metavar="LANG",
                    help="target language code, e.g. tr")
    tr.add_argument("--from", dest="from_lang", default="auto", metavar="LANG",
                    help="source language code; 'auto' lets the model decide")
    tr.add_argument("-o", "--output", default=None)
    tr.add_argument("--provider", choices=["openai", "deepl", "fake"], default="openai")
    tr.add_argument("--base-url", default="http://localhost:1234/v1",
                    help="OpenAI-compatible endpoint (LM Studio 1234, Ollama 11434)")
    tr.add_argument("--model", default=None)
    tr.add_argument("--api-key", default=None,
                    help="optional; LM Studio and Ollama do not require a real key")
    tr.add_argument("--timeout", type=float, default=None, metavar="SECONDS",
                    help="pin the per-request timeout. Omit it and the timeout adapts: a large "
                         "allowance while a cold model loads, then the throughput measured from "
                         "the first batch")
    tr.add_argument("--fit-mode", choices=["strict", "reflow"], default="strict",
                    help="strict keeps the original boxes; reflow lets blocks grow (PDF only)")
    tr.add_argument("--memory", default=None, metavar="PATH",
                    help="SQLite translation memory; reuses earlier translations of repeated text")
    tr.add_argument("--glossary", default=None, metavar="PATH",
                    help="JSON terminology file: {\"source term\": \"target term\"}")
    tr.add_argument("--limit", type=int, default=None, metavar="N",
                    help="translate only N segments (cheap smoke test)")
    tr.add_argument("--skip", type=int, default=0, metavar="N",
                    help="skip the first N segments; front matter is rarely representative "
                         "of a book's prose, so sampling from the middle measures better")
    tr.add_argument("--save-project", default=None, metavar="PATH",
                    help="also write a .lkproj file for later editing")
    tr.set_defaults(func=cmd_translate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
