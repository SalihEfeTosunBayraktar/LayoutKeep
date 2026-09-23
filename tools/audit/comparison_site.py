"""Build the side-by-side comparison site: every held-out document, original against translation.

The measurement pages say what the audit found; this one lets a person look. Each document becomes
a page of the site with a draggable divider over the two renderings of the same page - the original
and what came out of the pipeline - so a reader can see for themselves whether a page kept its
layout, its figures and its meaning.

Sources come from `_artifacts/heldout/sources/`, translations from the recorded campaign runs
(`<run>/<name>.tr.pdf` when a full document was assembled, else the per-chunk `out/t_*.pdf` in
order) plus the newest live run in `_artifacts/heldout/live/`.

    python tools/audit/comparison_site.py [--out docs/comparison] [--dpi 144] [--max-pages 8]

Everything is written under the output directory: `index.html` plus `img/<document>/<page>_{a,b}.jpg`.
No network, no CDN - the file opens from disk.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "_artifacts/heldout/sources"
RUNS = ROOT / "_artifacts/heldout/runs"
LIVE = ROOT / "_artifacts/heldout/live"
RUN_SCRIPT = ROOT / "_artifacts/heldout/run_heldout.sh"


def _run_sources() -> dict[str, str]:
    """Which file each run translated, taken from the campaign's own script.

    The run names and the source file names do not match (`arxiv_19113` is
    `arxiv_2609.19113.pdf`, `cookbook_1907` is `archive_cookbook_1907.pdf`), and the mapping only
    exists in the script that launched the runs. Reading it here means a run added to the campaign
    shows up on the site without a second list to keep in step.
    """
    if not RUN_SCRIPT.exists():
        return {}
    mapping: dict[str, str] = {}
    for line in RUN_SCRIPT.read_text(encoding="utf-8").splitlines():
        match = re.match(r"(?:pdf|single|\(\s*single)\s+(\S+)\s+(\S+)\.(pdf|epub|png|jpg)", line)
        if match:
            mapping[match.group(1)] = f"{match.group(2)}.{match.group(3)}"
    return mapping


def _source_for(run: Path, mapping: dict[str, str]) -> Path | None:
    named = mapping.get(run.name)
    if named and (SOURCES / named).exists():
        return SOURCES / named
    for candidate in (SOURCES / f"{run.name}.pdf", SOURCES / f"{run.name}_full.pdf"):
        if candidate.exists():
            return candidate
    return None


@dataclass
class Document:
    """One sample: page by page, where its original is and what came out for it, plus the audit."""

    name: str
    title: str
    pairs: list[tuple[Path, int, Path, int]]  # (original pdf, page, translation pdf, page)
    #: The audit's counts only, language-neutral (`L6 120, L7 2`), and whether an audit exists at
    #: all - the sentence around them belongs to the page, which knows the reader's language.
    losses: str = ""
    audited: bool = False
    #: A key the page words ("latest"), not a sentence: this file is generated once and read in
    #: whichever interface language the reader picks.
    note: str = ""
    origin: str = ""
    #: Commit the run was recorded at, and the same value kept only when it is not the commit the
    #: tree is on: a page kept from an older engine is honest evidence about *that* engine, and the
    #: site has to say so rather than let it pass for the current one.
    commit: str = ""
    stale: str = ""
    #: What made this translation and how it measured, for a bench run: version, commit, model,
    #: direction, quality, consistency, layout. Empty for a campaign run, which has no record.
    record: dict | None = None


def _translation_pdfs(run: Path) -> list[Path]:
    """The translated pages in order: the assembled document if there is one, else the chunks."""
    assembled = sorted(run.glob("*.tr.pdf"))
    if assembled:
        return [assembled[0]]
    return sorted(run.glob("out/t_*.pdf"))


def _sample_pages(total: int, cap: int) -> list[int]:
    """Which pages to show: the first, then evenly spread, never more than `cap`."""
    if total <= cap:
        return list(range(total))
    step = (total - 1) / (cap - 1)
    return sorted({round(i * step) for i in range(cap)})


def _head_commit() -> str:
    """The short commit the working tree is on, so a run can be dated against it.

    Read straight out of `.git` rather than through `git rev-parse`: this is a one-time label for
    the page, and a subprocess per document would cost more than it is worth. A linked worktree
    keeps its git directory elsewhere, in which case the label is simply left off.
    """
    try:
        head = (ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if head.startswith("ref: "):
        try:
            return (ROOT / ".git" / head.removeprefix("ref: ").strip()).read_text(
                encoding="utf-8"
            ).strip()[:7]
        except OSError:
            return ""
    return head[:7]


def _run_commit(run: Path) -> str:
    written = run / "commit.txt"
    return written.read_text(encoding="utf-8").strip()[:7] if written.exists() else ""


def _audit_state(run: Path) -> tuple[bool, str]:
    """Whether the run carries an audit, and the counts it found.

    The counts stay language-neutral (`L6 120, L7 2`) because both interface languages print the
    same criterion names; the sentence around them is built by the page, in whichever language
    the reader picked.
    """
    report = run / "audit.json"
    if not report.exists():
        return False, ""
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, ""
    counts = data.get("counts", {})
    if not counts:
        return False, ""
    # Only what was found, in criterion order: a row of zeroes tells a reader nothing, and the
    # order L1..L10 then D1..D3 is the one the report and the application use.
    order = [f"L{n}" for n in range(1, 11)] + [f"D{n}" for n in range(1, 4)]
    shown = [f"{kind} {counts[kind]}" for kind in order if counts.get(kind)]
    return True, ", ".join(shown)


def _campaign_documents() -> list[Document]:
    documents: list[Document] = []
    mapping = _run_sources()
    head = _head_commit()
    for run in sorted(RUNS.iterdir()):
        if not run.is_dir():
            continue
        if not _publishable(run):
            continue  # a source that must not be republished (see NOT_PUBLISHABLE)
        source = _source_for(run, mapping)
        if source is None or source.suffix.lower() != ".pdf":
            continue  # posters and epubs are covered by their own format's run, or not at all
        translated = _translation_pdfs(run)
        if not translated:
            continue
        with pymupdf.open(source) as original:
            original_pages = original.page_count
        pairs: list[tuple[Path, int, Path, int]] = []
        for path in translated:
            with pymupdf.open(path) as chunk:
                for index in range(chunk.page_count):
                    pairs.append((source, min(len(pairs), original_pages - 1), path, index))
        audited, losses = _audit_state(run)
        recorded = _run_commit(run)
        documents.append(
            Document(
                name=run.name,
                title=run.name.replace("_", " "),
                pairs=pairs,
                losses=losses,
                audited=audited,
                commit=recorded,
                stale=recorded if recorded and recorded != head else "",
                origin=f"sources/{source.name} + runs/{run.name}",
            )
        )
    return documents


#: Runs whose pages must not leave this machine. The user handed this book over for testing and it
#: is a commercial textbook: the site publishes page images, so republishing them would infringe on
#: it. The translation stays on disk, the site simply does not show it.
NOT_PUBLISHABLE = frozenset({"ross_stats"})


def _publishable(run: Path) -> bool:
    """False for a run recorded from a source that must not be republished."""
    stem = run.name.split("_")
    return not any("_".join(stem[:index]) in NOT_PUBLISHABLE for index in range(1, len(stem) + 1))


#: A run name carries how it was produced, not which document it is: `cookbook_1907_r2` is the
#: second re-run of `cookbook_1907`, and `fresh_pdfmt_r6_2` is the third chunk of the sixth
#: revision of `fresh_pdfmt`.
_RUN_SUFFIX = re.compile(r"(?:_r\d+)(?:_\d+)?$")


def _base_name(name: str) -> str:
    """The document a run directory belongs to, without the revision or chunk numbering."""
    return _RUN_SUFFIX.sub("", name) or name


def _live_documents(per_document: int = 12) -> list[Document]:
    """The freshest live run of each document, all of its chunks, as one entry.

    WHY THIS EXISTS: a live run is written chunk by chunk (`cookbook_1907_r2` holds chunk_0000.pdf
    and thirty-odd more), and showing one entry per chunk filled the sidebar with `cookbook_1907_0`,
    `..._1`, `..._2` - the same document four times, each looking like a separate sample. Grouping
    by the base name also lets a re-run *replace* the entry it is a re-run of, which is the whole
    point of running it again after a fix.
    """
    groups: dict[str, list[Path]] = {}
    for run in LIVE.iterdir():
        if run.is_dir() and _publishable(run):
            groups.setdefault(_base_name(run.name), []).append(run)

    head = _head_commit()
    documents: list[Document] = []
    for base, runs in sorted(groups.items()):
        newest = max(runs, key=lambda path: path.stat().st_mtime)
        sources = sorted((newest / "src").glob("chunk_*.pdf")) if (newest / "src").exists() else []
        outputs = sorted((newest / "out").glob("t_*.pdf")) if (newest / "out").exists() else []
        pairs: list[tuple[Path, int, Path, int]] = []
        for source, output in list(zip(sources, outputs, strict=False))[:per_document]:
            with pymupdf.open(output) as chunk:
                pairs.extend((source, page, output, page) for page in range(chunk.page_count))
        if not pairs:
            continue
        recorded = _run_commit(newest)
        audited, losses = _audit_state(newest)
        documents.append(
            Document(
                name=base,
                title=base,
                pairs=pairs,
                losses=losses,
                audited=audited,
                note="latest",
                commit=recorded,
                stale=recorded if recorded and recorded != head else "",
                origin=f"live/{newest.name}",
            )
        )
    return documents


def _bench_table(run_dir: Path) -> dict[str, tuple[str, str]]:
    """Per source, the layout share and loss count the bench wrote into BENCH.md."""
    rows: dict[str, tuple[str, str]] = {}
    table = run_dir / "BENCH.md"
    if not table.exists():
        return rows
    for line in table.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) > 5 and cells[1] in ("en->tr", "tr->en") and cells[-1].endswith("%"):
            losses = next((c.strip("*") for c in cells if c.startswith("**")), "")
            rows[cells[0]] = (cells[-1], losses)
    return rows


def _bench_documents(run_dir: Path) -> list[Document]:
    """Every source of one bench arm, each with the record of what translated it and its bars.

    The bench keeps the source pages it cut (`<name>/source.pdf`), the translation
    (`<name>/<name>.<to>.pdf`), the provenance of the arm and the judges' files per source, so the
    site can say for each page pair which version, commit and model produced it and how it scored.
    """
    table = _bench_table(run_dir)
    documents: list[Document] = []
    for folder in sorted(p for p in run_dir.iterdir() if (p / "bench.json").exists()):
        meta = json.loads((folder / "bench.json").read_text(encoding="utf-8"))
        direction = meta["direction"]
        translated = folder / f"{folder.name}.{direction.split('->')[1]}.pdf"
        source = folder / "source.pdf"
        if not translated.exists() or not source.exists():
            continue
        with pymupdf.open(source) as original, pymupdf.open(translated) as output:
            pages = min(original.page_count, output.page_count)
        prov = meta.get("provenance") or {}
        record = {
            "version": prov.get("app_version", ""),
            "commit": str(prov.get("commit", ""))[:7],
            "model": prov.get("model", ""),
            "direction": direction.replace("->", " → ").upper(),
            "date": str(prov.get("started", ""))[:10],
        }
        quality = folder / "quality.json"
        if quality.exists():
            scores = [float(row["score"]) for row in json.loads(quality.read_text(encoding="utf-8"))
                      if isinstance(row, dict) and "score" in row]
            if scores:
                record["quality"] = f"{sum(scores) / len(scores):.1f}"
        consistency = folder / "consistency.json"
        if consistency.exists():
            data = json.loads(consistency.read_text(encoding="utf-8"))
            if data.get("occurrences"):
                record["consistency"] = f"{100 * data['consistent'] / data['occurrences']:.0f}%"
        if folder.name in table:
            record["layout"], losses = table[folder.name]
        else:
            losses = ""
        documents.append(
            Document(
                name=folder.name,
                title=f"{folder.name} ({record['direction']})",
                pairs=[(source, i, translated, i) for i in range(pages)],
                losses="" if losses in ("", "0") else f"{losses} loss(es)",
                audited=True,
                record=record,
            )
        )
    return documents


def collect(include_live: bool = True) -> list[Document]:
    """Every sample, freshest first, with a re-run standing in for the run it replaced.

    The old run is not deleted - its page images are the evidence of what that engine produced -
    but it is not shown as a separate entry either once the same document has been run again on
    current code: two entries for one document read as two samples.
    """
    live = _live_documents() if include_live else []
    fresh = {document.name for document in live}
    campaign = [document for document in _campaign_documents() if document.name not in fresh]
    return live + campaign


def _save(pix, stem: Path) -> str:
    """Write one page render, as WebP when Pillow is available.

    Measured on the heaviest page (arXiv, formulas and figures): 168 dpi JPEG 191 KB, 168 dpi WebP
    410 KB, 144 dpi WebP 313 KB. WebP buys the resolution that a zoom needs (text stays readable at
    200% - checked by eye), so the defaults are 144 dpi at quality 80 with 8 pages per document,
    which keeps the whole site around a third of the size a 168 dpi JPEG set would take. WebP needs
    Pillow, which the OCR extra brings; without it the JPEG path is used and the site still works.
    """
    try:
        from PIL import Image
    except ImportError:
        pix.save(stem.with_suffix(".jpg"), jpg_quality=76)
        return stem.with_suffix(".jpg").name
    Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(
        stem.with_suffix(".webp"), "WEBP", quality=80, method=4
    )
    return stem.with_suffix(".webp").name


def render(document: Document, out_dir: Path, dpi: int, cap: int) -> list[dict]:
    """Write the before/after images for one document and return its page records."""
    folder = out_dir / "img" / document.name
    folder.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72
    records: list[dict] = []
    for page_number in _sample_pages(len(document.pairs), cap):
        source_path, source_index, output_path, output_index = document.pairs[page_number]
        with pymupdf.open(source_path) as original:
            before = original[min(source_index, original.page_count - 1)].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom)
            )
        before_name = _save(before, folder / f"{page_number:04d}_a")
        with pymupdf.open(output_path) as translated:
            after = translated[min(output_index, translated.page_count - 1)].get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom)
            )
        after_name = _save(after, folder / f"{page_number:04d}_b")
        records.append(
            {
                "page": page_number + 1,
                "before": f"img/{document.name}/{before_name}",
                "after": f"img/{document.name}/{after_name}",
            }
        )
    return records


#: Every word the page shows, in both languages, one place. The page itself is generated once and
#: read in either language, so the labels cannot live in the markup; and they are kept here rather
#: than in the JavaScript because this is where the rest of the generated data is built, and
#: because a JavaScript object literal inside a `str.format` template needs every brace doubled -
#: a trap that already cost one KeyError. `{count}`, `{dpi}` and `{origin}` are filled in below;
#: `{{c}}` is a commit the page substitutes at read time.
TEXT = {
    "en": {
        "title": "LayoutKeep — original and translation, side by side",
        "sub": "Drag the divider (or use ← →): the original on the left, the translated page on the right. Ctrl + wheel zooms. {count} documents.",
        "zoom_out": "Zoom out (Ctrl -)",
        "zoom_in": "Zoom in (Ctrl +)",
        "zoom_fit": "Fit",
        "zoom_fit_title": "Fit to width (0)",
        "zoom_hint": "Ctrl + wheel also zooms; once zoomed in the page scrolls.",
        "alt_before": "original page",
        "alt_after": "translated page",
        "tag_before": "original",
        "tag_after": "translation",
        "footer_hint": "Images at {dpi} dpi. Source: _artifacts/heldout/{origin}.",
        "dev_toggle": "show development runs",
        "pages": "pages",
        "stale": "recorded {{c}} (not current)",
        "audit": "audit",
        "no_findings": "lossless audit: nothing found",
        "note_latest": "latest code, real model",
        "quality": "quality",
        "consistency": "term consistency",
        "layout": "layout",
    },
    "tr": {
        "title": "LayoutKeep — orijinal ve çeviri, yan yana",
        "sub": "Ayırıcıyı sürükle (ya da ← → tuşları): solda orijinal, sağda çevrilmiş sayfa. Ctrl + tekerlek yakınlaştırır. {count} belge.",
        "zoom_out": "Uzaklaştır (Ctrl -)",
        "zoom_in": "Yakınlaştır (Ctrl +)",
        "zoom_fit": "Sığdır",
        "zoom_fit_title": "Genişliğe sığdır (0)",
        "zoom_hint": "Ctrl + tekerlek de yakınlaştırır; yakınlaşınca sayfa kaydırılır.",
        "alt_before": "orijinal sayfa",
        "alt_after": "çevrilmiş sayfa",
        "tag_before": "orijinal",
        "tag_after": "çeviri",
        "footer_hint": "Görseller {dpi} dpi. Kaynak: _artifacts/heldout/{origin}.",
        "dev_toggle": "geliştirme koşularını göster",
        "pages": "sayfa",
        "stale": "kayıt {{c}} (güncel değil)",
        "audit": "denetim",
        "no_findings": "kayıpsızlık denetimi: bulgu yok",
        "note_latest": "en güncel kod, gerçek model",
        "quality": "kalite",
        "consistency": "terim tutarlılığı",
        "layout": "düzen",
    },
}


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LayoutKeep — original and translation, side by side</title>
<style>
  :root {{ color-scheme: dark; --ink:#e8eaed; --muted:#9aa0a6; --line:#2b2f36; --accent:#4c8dff;
           --warn:#e0a458; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:15px/1.5 system-ui, "Segoe UI", sans-serif; background:#0f1115; color:var(--ink); }}
  header {{ padding:18px 22px; border-bottom:1px solid var(--line); position:sticky; top:0; background:#0f1115f2; backdrop-filter:blur(6px); z-index:5; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  .langs {{ position:absolute; top:18px; right:22px; display:flex; gap:6px; }}
  .langs button {{ padding:4px 10px; border-radius:6px; border:1px solid var(--line); background:#151922;
                   color:var(--muted); cursor:pointer; font:inherit; font-size:12px; }}
  .langs button.active {{ border-color:var(--accent); color:var(--ink); }}
  main {{ display:grid; grid-template-columns: 260px 1fr; gap:0; min-height: calc(100vh - 74px); }}
  nav {{ border-right:1px solid var(--line); padding:12px; overflow:auto; max-height: calc(100vh - 74px); }}
  nav button {{ display:block; width:100%; text-align:left; margin:0 0 6px; padding:8px 10px; border:1px solid var(--line);
                border-radius:8px; background:#151922; color:var(--ink); cursor:pointer; font:inherit; }}
  nav button.active {{ border-color:var(--accent); background:#1b2433; }}
  nav button small {{ display:block; color:var(--muted); font-size:11px; }}
  section {{ padding:16px 20px 40px; }}
  h2 {{ font-size:16px; margin:4px 0 2px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:12px; }}
  .meta.stale {{ color:var(--warn); }}
  .devtoggle {{ display: flex; gap: 6px; align-items: center; font-size: 12px; color: var(--muted-foreground); padding: 4px 2px; }}
.devtoggle input {{ accent-color: var(--accent); }}
nav button.stale {{ border-color:var(--warn); }}
  .viewport {{ overflow:auto; max-height:82vh; border:1px solid var(--line); border-radius:10px; background:#14171d; }}
  .stage {{ position:relative; width:100%; touch-action:none; cursor:ew-resize; }}
  .stage img {{ display:block; width:100%; height:auto; user-select:none; -webkit-user-drag:none; }}
  .stage .after {{ position:absolute; inset:0; }}
  .stage .before {{ position:relative; z-index:2; clip-path: inset(0 50% 0 0); }}
  .handle {{ position:absolute; top:0; bottom:0; left:50%; width:2px; background:var(--accent); z-index:3; }}
  .handle::after {{ content:""; position:absolute; top:50%; left:50%; width:34px; height:34px; margin:-17px 0 0 -17px;
                    border-radius:50%; border:2px solid var(--accent); background:#0f1115cc; }}
  .tag {{ position:absolute; top:10px; padding:3px 8px; border-radius:6px; font-size:12px; background:#0f1115cc; z-index:4; }}
  .tag.a {{ left:10px; }} .tag.b {{ right:10px; }}
  .pages {{ display:flex; flex-wrap:wrap; gap:6px; margin:12px 0 0; }}
  .pages button {{ padding:5px 9px; border-radius:6px; border:1px solid var(--line); background:#151922; color:var(--ink); cursor:pointer; font:inherit; font-size:13px; }}
  .pages button.active {{ border-color:var(--accent); background:#1b2433; }}
  .hint {{ color:var(--muted); font-size:12px; margin-top:8px; }}
  .zoom {{ display:flex; align-items:center; gap:8px; margin:10px 0 8px; }}
  .zoom button {{ min-width:34px; padding:5px 10px; border-radius:6px; border:1px solid var(--line); background:#151922;
                  color:var(--ink); cursor:pointer; font:inherit; font-size:14px; }}
  .zoom button:hover {{ border-color:var(--accent); }}
  .zoom .level {{ min-width:52px; text-align:center; color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }}
</style>
</head>
<body>
<header>
  <h1 data-i18n="title">LayoutKeep — original and translation, side by side</h1>
  <div class="sub" data-i18n="sub">Drag the divider (or use ← →): the original on the left, the translated page on the right. Ctrl + wheel zooms. {count} documents.</div>
  <div class="langs">
    <button type="button" data-lang="en">EN</button>
    <button type="button" data-lang="tr">TR</button>
  </div>
</header>
<main>
  <nav id="docs"></nav>
  <section>
    <h2 id="title"></h2>
    <div class="meta" id="meta"></div>
    <div class="zoom">
      <button id="zoom-out" title="Zoom out (Ctrl -)" data-i18n-title="zoom_out">−</button>
      <span class="level" id="zoom-level">100%</span>
      <button id="zoom-in" title="Zoom in (Ctrl +)" data-i18n-title="zoom_in">+</button>
      <button id="zoom-fit" title="Fit to width (0)" data-i18n="zoom_fit" data-i18n-title="zoom_fit_title">Fit</button>
      <span class="hint" data-i18n="zoom_hint">Ctrl + wheel also zooms; once zoomed in the page scrolls.</span>
    </div>
    <div class="viewport" id="viewport">
      <div class="stage" id="stage">
        <img class="before" id="before" alt="original page" data-i18n-alt="alt_before">
        <div class="after"><img id="after" alt="translated page" data-i18n-alt="alt_after"></div>
        <div class="tag a" data-i18n="tag_before">original</div>
        <div class="tag b" data-i18n="tag_after">translation</div>
        <div class="handle" id="handle"></div>
      </div>
    </div>
    <div class="pages" id="pages"></div>
    <div class="hint" data-i18n="footer_hint">Images at {dpi} dpi. Source: _artifacts/heldout/{origin}.</div>
  </section>
</main>
<script>
const DATA = {data};

// The labels arrive from the generator (`TEXT` in comparison_site.py) as one object per language:
// English is the default because this page is the project's public face, and Turkish is one
// click away - the same rule the application itself follows.
const TEXT = {text};

let current = 0, page = 0, dragging = false, ratio = 0.5, zoom = 1;
const $ = (id) => document.getElementById(id);

function applyLanguage(lang) {{
  const t = TEXT[lang] || TEXT.en;
  document.documentElement.lang = TEXT[lang] ? lang : "en";
  document.title = t.title;
  document.querySelectorAll("[data-i18n]").forEach((el) => {{
    const text = t[el.dataset.i18n];
    if (text) el.textContent = text;
  }});
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {{
    const text = t[el.dataset.i18nTitle];
    if (text) el.title = text;
  }});
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {{
    const text = t[el.dataset.i18nAlt];
    if (text) el.alt = text;
  }});
  document.querySelectorAll("[data-lang]").forEach((b) => {{
    b.classList.toggle("active", b.dataset.lang === document.documentElement.lang);
  }});
  renderNav();
  showDocument(current);
  try {{ localStorage.setItem("lk_lang", document.documentElement.lang); }} catch (e) {{ /* file:// may refuse */ }}
}}

function setRatio(value) {{
  ratio = Math.min(1, Math.max(0, value));
  $("before").style.clipPath = `inset(0 ${{(1 - ratio) * 100}}% 0 0)`;
  $("handle").style.left = `${{ratio * 100}}%`;
}}

function setZoom(value) {{
  zoom = Math.min(4, Math.max(0.25, value));
  $("stage").style.width = (zoom * 100) + "%";
  $("zoom-level").textContent = Math.round(zoom * 100) + "%";
}}

function showDocument(index) {{
  current = index; page = 0;
  const doc = DATA[index];
  const t = TEXT[document.documentElement.lang] || TEXT.en;
  $("title").textContent = doc.title;
  const audit = doc.audited ? (doc.losses ? t.audit + ": " + doc.losses : t.no_findings) : "";
  const note = doc.note ? t["note_" + doc.note] || "" : "";
  const stale = doc.stale ? t.stale.replace("{{c}}", doc.stale) : "";
  const r = doc.record;
  const record = r ? [r.direction, "LayoutKeep " + r.version + " (" + r.commit + ")", r.model,
    r.quality ? t.quality + " " + r.quality : "", r.consistency ? t.consistency + " " + r.consistency : "",
    r.layout ? t.layout + " " + r.layout : "", r.date].filter(Boolean).join(" · ") : "";
  $("meta").textContent = [doc.pages.length + " " + t.pages, record, audit, note, stale]
    .filter(Boolean).join(" · ");
  $("meta").classList.toggle("stale", Boolean(doc.stale));
  $("pages").replaceChildren(...doc.pages.map((record, i) => {{
    const button = document.createElement("button");
    button.textContent = record.page;
    button.onclick = () => showPage(i);
    return button;
  }}));
  [...$("docs").children].forEach((child, i) => child.classList.toggle("active", i === index));
  showPage(0);
}}

function showPage(index) {{
  page = index;
  const record = DATA[current].pages[index];
  $("before").src = record.before;
  $("after").src = record.after;
  [...$("pages").children].forEach((child, i) => child.classList.toggle("active", i === index));
}}

const stage = $("stage");
const move = (event) => {{
  const box = stage.getBoundingClientRect();
  const x = (event.touches ? event.touches[0].clientX : event.clientX) - box.left;
  setRatio(x / box.width);
}};
stage.addEventListener("pointerdown", (event) => {{ dragging = true; move(event); }});
window.addEventListener("pointerup", () => {{ dragging = false; }});
window.addEventListener("pointermove", (event) => {{ if (dragging) move(event); }});
$("zoom-in").onclick = () => setZoom(zoom * 1.25);
$("zoom-out").onclick = () => setZoom(zoom / 1.25);
$("zoom-fit").onclick = () => setZoom(1);
$("viewport").addEventListener("wheel", (event) => {{
  if (!event.ctrlKey) return;  // plain wheel still scrolls the page
  event.preventDefault();
  setZoom(zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15));
}}, {{ passive: false }});
window.addEventListener("keydown", (event) => {{
  if (event.key === "ArrowLeft") showPage(Math.max(0, page - 1));
  if (event.key === "ArrowRight") showPage(Math.min(DATA[current].pages.length - 1, page + 1));
  if (event.key === "+" || event.key === "=") setZoom(zoom * 1.25);
  if (event.key === "-" || event.key === "_") setZoom(zoom / 1.25);
  if (event.key === "0") setZoom(1);
}});

const nav = $("docs");
// The sidebar is the shop window: the `fresh_*` entries are the fixture runs this project uses
// to measure itself (one page each, named after the fixture), not documents anyone came to read.
// They stay one checkbox away rather than gone, because they are the evidence behind the
// numbers in the reports.
const toggle = document.createElement("label");
toggle.className = "devtoggle";
toggle.innerHTML = `<input type="checkbox" id="showdev"> <span data-i18n="dev_toggle">show development runs</span>`;
nav.append(toggle);
toggle.querySelector("input").onchange = () => renderNav();

function renderNav() {{
  [...nav.querySelectorAll("button")].forEach((b) => b.remove());
  const showDev = toggle.querySelector("input").checked;
  DATA.forEach((doc, index) => {{
    if (doc.dev && !showDev) return;
    const button = document.createElement("button");
    const t = TEXT[document.documentElement.lang] || TEXT.en;
    const stale = doc.stale ? " · " + t.stale.replace("{{c}}", doc.stale) : "";
    button.innerHTML = `${{doc.title}}<small>${{doc.pages.length}} ${{t.pages}}${{stale}}</small>`;
    button.classList.toggle("stale", Boolean(doc.stale));
    button.onclick = () => showDocument(index);
    nav.append(button);
  }});
}}
renderNav();
setRatio(0.5);
document.querySelectorAll("[data-lang]").forEach((b) => {{ b.onclick = () => applyLanguage(b.dataset.lang); }});
let initial = "en";
try {{ initial = localStorage.getItem("lk_lang") || "en"; }} catch (e) {{ /* file:// may refuse */ }}
applyLanguage(initial);
showDocument(DATA.findIndex((d) => !d.dev) || 0);
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/comparison")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--bench", type=Path, default=None,
                        help="build from one bench arm (_artifacts/bench/<arm>) with its records")
    args = parser.parse_args()

    documents = _bench_documents(args.bench) if args.bench else collect(include_live=not args.no_live)
    if not documents:
        print("no documents found under _artifacts/heldout", file=sys.stderr)
        return 1

    site: list[dict] = []
    for document in documents:
        pages = render(document, args.out, args.dpi, args.max_pages)
        print(f"{document.name:32} {len(pages):3} pages")
        site.append(
            {
                "title": document.title,
                "losses": document.losses,
                "audited": document.audited,
                "note": document.note,
                "stale": document.stale,
                "record": document.record,
                "dev": document.name.startswith("fresh_") or "_smoke" in document.name,
                "pages": pages,
            }
        )

    args.out.mkdir(parents=True, exist_ok=True)
    origin = f"bench/{args.bench.name}" if args.bench else "sources + runs + live"
    # The labels are filled in here, once: `{c}` stays literal (it is a commit the page substitutes
    # when a run is older than the tree) while the counts, dpi and origin are known right now.
    labels = {
        lang: {
            key: value.format(count=len(site), dpi=args.dpi, origin=origin)
            for key, value in entries.items()
        }
        for lang, entries in TEXT.items()
    }
    (args.out / "index.html").write_text(
        PAGE_TEMPLATE.format(
            data=json.dumps(site, ensure_ascii=False),
            text=json.dumps(labels, ensure_ascii=False),
            count=len(site),
            dpi=args.dpi,
            origin=origin,
        ),
        encoding="utf-8",
    )
    images = sum(1 for pattern in ("*.webp", "*.jpg") for _ in (args.out / "img").rglob(pattern))
    print(f"\n{len(site)} documents, {images} images -> {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
