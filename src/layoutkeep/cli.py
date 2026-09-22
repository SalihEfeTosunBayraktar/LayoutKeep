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

from layoutkeep.core import review, tunables
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


def _read_document(path: Path, classifier=None, layout=None) -> Document:
    # Dokümanı veya görseli DocIR'e okur / Reads document or image into DocIR
    from layoutkeep.writers.converter import read_any_document

    suffix = path.suffix.lower()
    try:
        return read_any_document(path, classifier=classifier, layout=layout)
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

    Inside it, repeated text is shared between its occurrences (`providers/dedupe.py`), so a form
    whose header repeats on every page is translated once and reads the same on every page.
    """
    from layoutkeep.providers.dedupe import DedupeProvider

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

        model_name = args.model or "google/gemma-4-e4b"
        provider = OpenAICompatProvider(
            base_url=args.base_url, model=model_name, api_key=args.api_key,
            timeout=args.timeout,
        )
        model_id = f"{args.base_url}:{model_name}"

    from layoutkeep.providers.protected import ProtectedProvider

    if not args.memory:
        return ProtectedProvider(DedupeProvider(provider, enabled=_reuse_repeats(args))), None

    from layoutkeep.providers.cached import CachedProvider
    from layoutkeep.providers.memory import TranslationMemory

    memory = TranslationMemory(args.memory)
    return (
        ProtectedProvider(
            CachedProvider(DedupeProvider(provider, enabled=_reuse_repeats(args)), memory, model_id)
        ),
        memory,
    )


def _automatic_glossary(doc: Document, provider, args: argparse.Namespace) -> dict[str, str]:
    """The document's own terms, rendered once, when `translation.auto_glossary` is on (D-007).

    Empty when the setting is off, when the provider has no chat call to ask with (DeepL), or when
    the model's answer cannot be read: the run then translates exactly as it did before.
    """
    if not bool(tunables.get("translation.auto_glossary")):
        return {}

    from layoutkeep.core.doc_glossary import build_doc_glossary
    from layoutkeep.providers.base import chat_callable

    chat = chat_callable(provider)
    if chat is None:
        print("glossary  this provider has no chat call - no automatic terms")
        return {}

    def ask(system: str, user: str) -> str:
        return str(
            chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        )

    automatic = build_doc_glossary(doc, ask, source_lang=args.from_lang, target_lang=args.to_lang)
    if not automatic:
        print("glossary  no automatic terms came back")
    return automatic


def _reuse_repeats(args: argparse.Namespace) -> bool:
    """Whether text this document repeats is translated once (`providers/dedupe.py`).

    Inside the protection wrapper, so the shared text is the tokenised text: two lines differing
    only in the numbers they state are one request, and each restores its own values.
    """
    if getattr(args, "no_repeats", False):
        return False
    return bool(tunables.get("translation.reuse_repeats"))


def _dedupe_stats(provider: object) -> dict[str, int]:
    """What the repeat-sharing wrapper did, wherever it sits in the provider chain."""
    seen: set[int] = set()
    while provider is not None and id(provider) not in seen:
        seen.add(id(provider))
        totals = getattr(provider, "totals", None)
        if isinstance(totals, dict) and "saved" in totals:
            return {"saved": int(totals["saved"]), "shared": int(totals.get("shared", 0))}
        provider = getattr(provider, "inner", None)
    return {"saved": 0, "shared": 0}


# --------------------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------------------


def _layout_classifier(args: argparse.Namespace):
    """The vision model that says what each region of a scanned page is, or None.

    Off by default: it is one request per page, and a document with a text layer does not need
    it - the fonts already say what is a heading and what is an equation. On a scan they are the
    only thing that does. Measured over ten pages of a 524-page scan, it took the font-size
    spread from 1.16 to 1.00 and left every other reading unchanged (see ocr/layout_vlm.py).
    """
    model = getattr(args, "classify_layout", None)
    if not model:
        return None
    from layoutkeep.ocr.layout_vlm import openai_vision_chat

    return openai_vision_chat(args.base_url, model)


def _layout_detector(args: argparse.Namespace):
    """The local layout model, or None.

    Used whenever it is installed (a 171 MB model file, see ocr/layout_detector.py): every
    result of the translation campaign was measured with it, on born-digital pages and scans
    alike, so reading without it is reading worse than the project knows how to.
    `--no-layout-detector` turns it off. `--layout-detector` requires it: asked for and missing
    is an error rather than a silent fallback, so a run believed to use the model cannot quietly
    not use it.
    """
    choice = getattr(args, "layout_detector", None)
    if choice is False:
        return None
    from layoutkeep.ocr.layout_detector import default_model_path, load_detector

    detector = load_detector()
    if detector is None and choice is True:
        raise SystemExit(f"layout model not found or not loadable: {default_model_path()}")
    return detector


def cmd_inspect(args: argparse.Namespace) -> int:
    """Show what the reader actually understood. This is the phase-0 debugging workhorse.

    Role misclassification (a running header read as body text, a page number read as a heading)
    is the single most common way layout-preserving translation goes wrong, and it is invisible
    until you look at the counts.
    """
    src = Path(args.input)
    doc = _read_document(src, _layout_classifier(args), _layout_detector(args))
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

    # The same policy the desktop application applies, from the same module. A conversion that
    # is locked there and runs here would be the CLI quietly shipping output the project has
    # measured and does not stand behind.
    from layoutkeep.core import capabilities

    if not capabilities.is_open(src.suffix, out.suffix):
        raise SystemExit(
            f"{src.suffix} to {out.suffix} is not enabled in this build. The open pairs are "
            "PDF→PDF, PDF→DOCX, EPUB→EPUB, DOCX→DOCX and PNG→DOCX. "
            "The measurements behind that are in docs/ENGINE-ARCHITECTURE.md, and "
            "tools/audit/format_matrix.py reproduces them."
        )

    phases = _Phases()
    print(f"reading   {src}")
    doc = _read_document(src, _layout_classifier(args), _layout_detector(args))
    phases.mark("read")
    doc.source_lang = args.from_lang
    doc.target_lang = args.to_lang

    if preserve_references_from(args):
        from layoutkeep.core.reference import tag_bibliography_blocks

        tagged = tag_bibliography_blocks(doc, preserve=True)
        if tagged:
            print(f"references {tagged} bibliography blocks preserved untouched")

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

    # D-007: the document's terms, asked once and merged with the file the user gave. The merged
    # list is what is translated, re-asked and checked below, so a term is settled for every
    # occurrence rather than rendered differently each time the model meets it.
    automatic = _automatic_glossary(doc, provider, args)
    if automatic:
        from layoutkeep.core.doc_glossary import merge_glossaries, write_glossary
        from layoutkeep.providers.glossary import Glossary

        from_file = len(glossary.terms) if glossary else 0
        merged = merge_glossaries(automatic, glossary.terms if glossary else None)
        target = write_glossary(merged, out.with_name(f"{out.stem}.glossary.json"))
        glossary = Glossary(merged)
        print(f"glossary  {len(automatic)} automatic terms (+{from_file} from the file)")
        print(f"terms     {target}")

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
    phases.mark("translate")

    stats = getattr(provider, "last_stats", None)
    if stats and (stats["protected"] or stats["skipped"]):
        note = f"protect   {stats['protected']} literal values held back from the model"
        if stats["skipped"]:
            note += f", {stats['skipped']} data-only segments answered without a request"
        if stats["lost"]:
            note += f", {stats['lost']} NOT returned - those segments flagged"
        print(note)

    from layoutkeep.providers.passthrough import flag_passthrough, flag_untranslated
    from layoutkeep.providers.retry import retry_untranslated

    # Before flagging anything: a segment with no reply is usually one the parser could not line
    # up with its batch, not text the model refuses. Asking again - in the small batch the
    # leftovers make - recovers most of them. Exactly one extra pass.
    recovered = retry_untranslated(
        provider,
        translated,
        src_lang=args.from_lang,
        tgt_lang=args.to_lang,
        glossary=glossary.terms if glossary else None,
    )
    if recovered:
        print(f"retry     {recovered} segments recovered on a second attempt")

    # One source text, one translation across the document (core/repeats.py). The provider shares
    # repeated text between its occurrences, so most of this is already true by the time we get
    # here; what it catches came from a memory entry, a resumed run or a repair round.
    from layoutkeep.core.repeats import unify_repeats

    unified = unify_repeats(translated, args.to_lang)
    if unified["rewritten"]:
        print(
            f"repeats   {unified['rewritten']} segment(s) reworded to match the same source "
            f"translated elsewhere ({unified['groups']} text(s) disagreed)"
        )
        for source, kept in unified["examples"]:
            print(f"          {source!r} -> {kept!r}")

    shared = _dedupe_stats(provider)
    if shared["saved"]:
        print(
            f"shared    {shared['saved']} repeated segment(s) answered from their first "
            f"occurrence instead of being sent again"
        )

    handed_back = flag_passthrough(translated)
    if handed_back:
        print(f"passthrough {handed_back} segments came back untranslated - flagged for review")

    # A segment with no reply is not written as a blank - it keeps the block's source text, so
    # the output document contains that paragraph in the wrong language. The `translated N/M`
    # count above is the only other sign of it, and it reads like a rounding loss.
    missing = flag_untranslated(translated)
    if missing:
        print(
            f"untranslated {missing} segments got no reply - their SOURCE TEXT stays in the "
            f"output document, flagged for review"
        )

    if glossary:
        translated, report = glossary.verify(translated)
        checked, honoured = report["checked"], report["honoured"]
        if checked:
            print(f"glossary  {honoured}/{checked} term occurrences honoured"
                  f"{' - rest flagged for review' if honoured < checked else ''}")

    done = sum(1 for s in translated if s.translated)
    cached = sum(1 for s in translated if s.from_memory)
    print(f"translated {done}/{len(translated)} in {elapsed:.1f}s"
          f"  cached={cached}")

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
        phases.mark("fit")
        if fit_stats:
            # `off_figure` counts boxes that were narrowed, not a fit layer, so it is kept out of
            # the block total the layers add up to.
            layers = {k: v for k, v in fit_stats.items() if k != "off_figure"}
            total = sum(layers.values())
            parts = " ".join(f"{k}={v}" for k, v in layers.items() if v)
            print(f"fitting   {total} blocks: {parts}")
            if fit_stats.get("off_figure"):
                print(f"          {fit_stats['off_figure']} box(es) narrowed to stay off a figure")
            if fit_stats.get("overflow"):
                print(f"          {fit_stats['overflow']} still overflow - flagged for review")

    orphans = apply_segments(doc, translated)
    # needs_review is counted here, after apply_segments: that is the step that raises the
    # flag on a translation which dropped its inline markers (bold/italic lost). Counting it
    # earlier reported 0 while the markers line above said "still wrong" - two numbers in the
    # same report contradicting each other.
    review = sum(1 for s in translated if s.needs_review)
    print(f"review    {review} segment(s) flagged for review")
    if orphans:
        print(f"WARNING   {len(orphans)} translated segments did not match any block: "
              f"{orphans[:5]}{'...' if len(orphans) > 5 else ''}")

    written = _write_document(doc, src, out)
    phases.mark("write")
    if len(written) > 1:
        # An image target writes one file per page, so naming only `out` would understate it.
        print(f"wrote     {len(written)} files, {written[0]} .. {written[-1].name}")
    else:
        print(f"wrote     {out}")

    if getattr(args, "dual", None) and src.suffix.lower() == ".pdf" and out.suffix.lower() == ".pdf":
        # Composing runs *after* the translated PDF is written and *before* verification, so the
        # audit keeps checking the single-language output (its page pairing stays valid) and the
        # bilingual file is a separate artifact beside it.
        from layoutkeep.writers.dual_pdf import compose_dual

        dual_path = out.with_name(f"{out.stem}.dual{out.suffix}")
        composed = compose_dual(src, out, dual_path, args.dual)
        print(f"dual      {dual_path} ({composed} pages, mode={args.dual})")

    _verify(doc, translated, src, out, provider, glossary, args, phases)
    print(f"spent     {phases.line()}  (total {phases.total():.1f}s)")

    if args.save_project:
        proj = Path(args.save_project)
        save_project(doc, proj)
        print(f"project   {proj}")

    return EXIT_OK



class _Phases:
    """Wall clock per phase, so "it felt slow" becomes a number to look at.

    The stage that dominates is not obvious from the outside and is not the same for every
    document: translation is the model's time, but fitting and writing are this program's, and on
    a long book they grow with the page count. Every run now ends with the split.
    """

    def __init__(self) -> None:
        self._marks: list[tuple[str, float]] = []
        self._last = time.monotonic()

    def mark(self, phase: str) -> None:
        now = time.monotonic()
        self._marks.append((phase, now - self._last))
        self._last = now

    def note(self, extra: dict[str, float]) -> None:
        """Add phases measured elsewhere (the repair pass measures itself)."""
        self._marks.extend(sorted(extra.items(), key=lambda item: item[1], reverse=True))

    def line(self) -> str:
        return " | ".join(f"{phase} {seconds:.1f}s" for phase, seconds in self._marks)

    def total(self) -> float:
        return sum(seconds for _phase, seconds in self._marks)

def _verify(doc: Document, translated, src: Path, out: Path, provider, glossary, args, phases=None) -> None:
    """Check what was written, ask again for what a translation lost, flag what remains.

    The same pass the desktop worker runs (layoutkeep/verify.py). The output itself is checked
    for PDF to PDF; every target gets the translation checks.
    """
    from layoutkeep.providers.retry import retry_untranslated
    from layoutkeep.verify import LABELS, verify_and_repair

    pdf_to_pdf = src.suffix.lower() == ".pdf" and out.suffix.lower() == ".pdf"

    def ask_again(again) -> int:
        return retry_untranslated(
            provider, again, src_lang=args.from_lang, tgt_lang=args.to_lang,
            glossary=glossary.terms if glossary else None,
        )

    def write_document() -> None:
        _write_document(doc, src, out)
        if phases is not None:
            phases.mark("write")

    report = verify_and_repair(
        doc,
        translated,
        target_lang=args.to_lang,
        write=write_document,
        source_pdf=src if pdf_to_pdf else None,
        output_pdf=out if pdf_to_pdf else None,
        ask_again=ask_again if args.verify_rounds > 0 else None,
        refit=(lambda again: _fit_pdf(doc, again, provider, args)) if src.suffix.lower() == ".pdf" else None,
        rounds=args.verify_rounds,
    )
    if phases is not None:
        phases.mark("verify")
    line = f"verify    {report.checked_blocks} blocks checked"
    if report.repaired:
        line += f", {report.repaired} mended by asking again - output written again"
    print(line + (", no losses found" if report.lossless else ""))
    for kind in sorted(report.remaining):
        print(f"          {kind} {LABELS[kind]}: {report.remaining[kind]} - flagged for review")


def fit_mode_from(args):
    """The fitting mode in force: the flag when given, otherwise the setting the app reads too.

    Kept as a function so it can be tested without a run, and so the CLI and the desktop worker
    cannot drift into different modes for the same document - which is what had happened (the
    worker was pinned to strict, so the reflow path was unreachable from the application).
    """
    from layoutkeep.fitting import FitMode

    chosen = getattr(args, "fit_mode", None) or (
        "reflow" if tunables.get("fitting.reflow") else "strict"
    )
    return FitMode.REFLOW if chosen == "reflow" else FitMode.STRICT


def preserve_references_from(args) -> bool:
    """Whether the reference list is left untranslated: the flag when given, otherwise the setting.

    The flag was the only way in, so the application could not do this at all. A function for the
    same reason as `fit_mode_from`: it can be tested without a run, and the command line and the
    desktop worker read one setting instead of drifting into different answers.
    """
    return bool(getattr(args, "preserve_references", False)) or bool(
        tunables.get("translation.preserve_references")
    )


def _fit_pdf(doc: Document, segments, provider, args) -> dict[str, int] | None:
    """Make the translated text fit its original boxes. PDF only - EPUB reflows by itself.

    Delegates to `fitting.pdf_pass`, the one pass the desktop worker runs too (a GUI that
    drifts from the CLI here is a bug, not a feature - both must fit identically).
    """
    from layoutkeep.fitting.pdf_pass import fit_pdf_pass

    def retranslate(segment, budget: int) -> str:
        """Ask the provider for a shorter rendering of one segment, within `budget` characters."""
        segment.max_len = budget
        again = provider.translate(
            [segment], src_lang=args.from_lang, tgt_lang=args.to_lang, glossary=None
        )
        return again[0].target if again and again[0].target else segment.target

    # The flag wins when it is given; otherwise the same setting the application reads decides,
    # so the two cannot disagree about how a document is fitted (they did: the CLI could reflow
    # while the application always used strict).
    mode = fit_mode_from(args)

    def on_fitted(seg, block, result) -> None:
        # fit_segment is pure - it reports what would fit. Writing the result back is ours.
        seg.target = result.text
        if result.needs_review:
            seg.needs_review = True
            seg.review_reason = review.sentence(result.review_reason) or (
                "çeviri kutuya sığmadı, küçültme yetmedi"
            )
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
    # Windows IPv6 SynSent gecikmesini onlemek icin 127.0.0.1 / Use 127.0.0.1 to avoid Windows IPv6 timeout
    mdl.add_argument("--base-url", default="http://127.0.0.1:1234/v1",
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
    tr.add_argument("--base-url", default="http://127.0.0.1:1234/v1",
                    help="OpenAI-compatible endpoint (LM Studio 1234, Ollama 11434)")
    tr.add_argument("--model", default="google/gemma-4-e4b",
                    help="model name (default: google/gemma-4-e4b)")
    tr.add_argument("--api-key", default=None,
                    help="optional; LM Studio and Ollama do not require a real key")
    tr.add_argument("--timeout", type=float, default=None, metavar="SECONDS",
                    help="pin the per-request timeout. Omit it and the timeout adapts: a large "
                         "allowance while a cold model loads, then the throughput measured from "
                         "the first batch")
    tr.add_argument(
        "--no-repeats",
        dest="no_repeats",
        action="store_true",
        help="translate every occurrence of repeated text instead of sharing one translation "
             "between them (see providers/dedupe.py; the sharing is on by default)",
    )
    tr.add_argument(
        "--classify-layout",
        metavar="MODEL",
        help="a vision model that labels each region of a SCANNED page (heading, formula, "
             "running header, ...). One request per page; needs a server that accepts images",
    )
    tr.add_argument(
        "--layout-detector",
        dest="layout_detector", action="store_const", const=True, default=None,
        help="require the local layout model (ocr/layout_detector.py); it is used whenever "
             "installed, this makes a missing model an error",
    )
    tr.add_argument(
        "--no-layout-detector",
        dest="layout_detector", action="store_const", const=False,
        help="read without the local layout model even when it is installed",
    )
    tr.add_argument("--verify-rounds", type=int, default=2, metavar="N",
                    help="after writing, check the output for losses and ask the model again "
                         "for lost text up to N times; what remains is flagged for review "
                         "(0 checks and flags without asking again)")
    tr.add_argument(
        "--dual",
        choices=["side", "alternate"],
        default=None,
        metavar="MODE",
        help=(
            "Ayrıca çift dilli bir PDF yaz: 'side' her sayfada kaynak solda çeviri sağda, "
            "'alternate' her kaynak sayfadan sonra çevirisi. Çevrilmiş PDF ve denetim değişmez."
        ),
    )
    tr.add_argument("--fit-mode", choices=["strict", "reflow"], default=None,
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
    tr.add_argument("--preserve-references", action="store_true", default=False,
                    help="preserve academic bibliography and citation sections without translating them")
    tr.add_argument("--checkpoint-interval", type=int, default=0, metavar="N",
                    help="periodically save translation progress to .lkproj every N segments (0 disables)")
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
